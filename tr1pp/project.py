"""Portable, atomic project storage. Project files never contain executable objects."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
from io import BytesIO
import copy
import hashlib
import json
import math
import os
import tempfile
import zipfile
import pretty_midi

FORMAT = 'tr1pp-project-v2'
MAX_BYTES = 512 * 1024 * 1024

@dataclass
class TrackMix:
    volume: float = .8
    pan: float = 0.
    mute: bool = False
    solo: bool = False
    # Seconds and linear gain; linearly interpolated by the renderer.
    automation: list[list[float]] = field(default_factory=list)
    effects: dict[str,float] = field(default_factory=dict)

    def validate(self):
        if not math.isfinite(self.volume) or not 0 <= self.volume <= 2:
            raise ValueError('Track volume must be between 0 and 2')
        if not math.isfinite(self.pan) or not -1 <= self.pan <= 1:
            raise ValueError('Track pan must be between -1 and 1')
        limits={'lowpass_hz':(0,20000),'delay_mix':(0,1),'delay_seconds':(.02,2),'reverb_mix':(0,1)}
        for key,value in self.effects.items():
            if key not in limits or not math.isfinite(value) or not limits[key][0]<=value<=limits[key][1]:
                raise ValueError('Invalid track effect: '+key)
        last = -1.
        for time, value in self.automation:
            if not math.isfinite(time) or time < 0 or time <= last:
                raise ValueError('Automation times must increase')
            if not math.isfinite(value) or not 0 <= value <= 2:
                raise ValueError('Automation gain must be between 0 and 2')
            last = time

@dataclass
class Project:
    midi: pretty_midi.PrettyMIDI = field(default_factory=pretty_midi.PrettyMIDI)
    sources: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    mixer: list[TrackMix] = field(default_factory=list)
    markers: list[dict] = field(default_factory=list)
    title: str = 'Untitled'
    # Embedded source blobs, keyed by original source identifier, retained on save.
    assets: dict[str, bytes] = field(default_factory=dict, repr=False)
    source_names: dict[str,str] = field(default_factory=dict)

    def sync_tracks(self):
        self.mixer = (self.mixer + [TrackMix() for _ in self.midi.instruments])[:len(self.midi.instruments)]


def _midi_bytes(midi):
    output = BytesIO(); midi.write(output); return output.getvalue()


def _encode_track(ins):
    return {'name':ins.name, 'program':int(ins.program), 'is_drum':bool(ins.is_drum),
            'notes':[[int(n.velocity),int(n.pitch),float(n.start),float(n.end)] for n in ins.notes],
            'control_changes':[[int(e.number),int(e.value),float(e.time)] for e in ins.control_changes],
            'pitch_bends':[[int(e.pitch),float(e.time)] for e in ins.pitch_bends]}


def _decode_track(data):
    program = data['program']
    if not isinstance(program,int) or not 0 <= program <= 127: raise ValueError('Invalid project instrument')
    ins = pretty_midi.Instrument(program, is_drum=bool(data.get('is_drum')), name=str(data.get('name','')))
    for velocity,pitch,start,end in data['notes']:
        if not 1 <= velocity <= 127 or not 0 <= pitch <= 127 or not all(math.isfinite(v) for v in (start,end)) or start < 0 or end <= start:
            raise ValueError('Invalid project note')
        ins.notes.append(pretty_midi.Note(int(velocity),int(pitch),float(start),float(end)))
    for number,value,time in data.get('control_changes',[]):
        if not 0 <= number <= 127 or not 0 <= value <= 127 or not math.isfinite(time) or time < 0:
            raise ValueError('Invalid project controller')
        ins.control_changes.append(pretty_midi.ControlChange(int(number),int(value),float(time)))
    for pitch,time in data.get('pitch_bends',[]):
        if not -8192 <= pitch <= 8191 or not math.isfinite(time) or time < 0: raise ValueError('Invalid project pitch bend')
        ins.pitch_bends.append(pretty_midi.PitchBend(int(pitch),float(time)))
    return ins


def save_project(project: Project, path, *, embed_sources=True):
    """Write to a sibling file, fsync, then atomically replace the destination."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    project.sync_tracks()
    for mix in project.mixer: mix.validate()
    manifest = dict(format=FORMAT, title=project.title, sources=[], settings=project.settings,
                    report=project.report, mixer=[asdict(m) for m in project.mixer],
                    markers=project.markers, tracks=[_encode_track(i) for i in project.midi.instruments])
    blobs = {'arrangement.mid': _midi_bytes(project.midi)}
    for source in dict.fromkeys(project.sources + list(project.assets)):
        record = {'original': source, 'name': project.source_names.get(source,Path(source).name), 'active': source in project.sources}
        content = project.assets.get(source)
        if content is None and embed_sources and Path(source).is_file():
            if Path(source).stat().st_size > MAX_BYTES: raise ValueError('Source exceeds project size limit')
            if sum(map(len,blobs.values()))+Path(source).stat().st_size>MAX_BYTES:raise ValueError('Project exceeds 512 MiB limit')
            content = Path(source).read_bytes()
        if content is not None:
            digest = hashlib.sha256(content).hexdigest()
            name = 'sources/' + digest + Path(source).suffix.lower()
            blobs[name] = content
            record.update(asset=name, sha256=digest)
        manifest['sources'].append(record)
    blobs['project.json'] = json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if sum(map(len, blobs.values())) > MAX_BYTES: raise ValueError('Project exceeds 512 MiB limit')
    fd, tmp = tempfile.mkstemp(prefix='.'+path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w+b') as handle:
            with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for name, value in blobs.items(): z.writestr(name, value)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return path


def load_project(path) -> Project:
    path = Path(path)
    if not zipfile.is_zipfile(path):
        # Read-only migration of the original v1 sidecar format.
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('format') != 'tr1pp-project-v1': raise ValueError('Unsupported project format')
        midi_path = data.get('export_midi')
        if midi_path:
            midi_path = Path(midi_path)
            if not midi_path.is_absolute(): midi_path = path.parent / midi_path
            midi = pretty_midi.PrettyMIDI(str(midi_path))
        else: midi = pretty_midi.PrettyMIDI()
        project = Project(midi=midi, sources=data.get('sources', []), settings=data.get('settings', {}))
        project.sync_tracks(); return project
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)): raise ValueError('Duplicate project members')
        if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError('Project exceeds safety limits')
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise ValueError('Unsafe project member')
        data = json.loads(z.read('project.json'))
        if data.get('format') != FORMAT: raise ValueError('Unsupported project format')
        midi = pretty_midi.PrettyMIDI(BytesIO(z.read('arrangement.mid')))
        if 'tracks' in data: midi.instruments = [_decode_track(t) for t in data['tracks']]
        project = Project(midi=midi, title=data.get('title', 'Untitled'),
                          settings=data.get('settings', {}), report=data.get('report', {}),
                          markers=data.get('markers', []))
        for entry in data.get('sources', []):
            original = entry['original']
            project.source_names[original]=entry.get('name',Path(original).name)
            if entry.get('active',True): project.sources.append(original)
            if entry.get('asset'):
                content = z.read(entry['asset'])
                if hashlib.sha256(content).hexdigest() != entry.get('sha256'):
                    raise ValueError('Source checksum mismatch')
                project.assets[original] = content
        project.mixer = [TrackMix(**record) for record in data.get('mixer', [])]
        project.sync_tracks()
        for mix in project.mixer: mix.validate()
        return project


def materialize_sources(project, directory, *, strict=True):
    """Restore embedded sources into a content-addressed workspace without overwrites."""
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    result = []
    for original in project.sources:
        blob = project.assets.get(original)
        if blob is None:
            if strict and not Path(original).is_file(): raise FileNotFoundError('Missing source: '+original)
            result.append(original); continue
        digest = hashlib.sha256(blob).hexdigest()
        path = directory / (digest + Path(original).suffix.lower())
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            fd, tmp = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(fd, 'wb') as out: out.write(blob)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        result.append(str(path))
    return result


def snapshot(project, directory, keep=12):
    """Timestamped recovery/history snapshot, retaining bounded history."""
    from datetime import datetime, timezone
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    result = save_project(project, directory / (stamp+'.tr1pp'))
    for old in sorted(directory.glob('*.tr1pp'))[:-max(1, keep)]: old.unlink()
    return result
