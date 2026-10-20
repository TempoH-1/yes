"""Pretrained Basic Pitch ONNX transcription with bounded decode and provenance.

Confidence is the model's note activation, not a calibrated probability of a
correct piano note. Basic Pitch is general-purpose and is not a dedicated
virtuoso-piano transcription model.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import os
import numpy as np
import pretty_midi
import soundfile as sf

@dataclass(frozen=True)
class TranscriptionOptions:
    onset_threshold: float = .5
    frame_threshold: float = .3
    minimum_note_ms: float = 90
    minimum_pitch: int = 21
    maximum_pitch: int = 108
    minimum_confidence: float = .15
    max_seconds: float = 600
    split_hands: bool = True

    def validate(self):
        for v in (self.onset_threshold,self.frame_threshold,self.minimum_confidence):
            if not math.isfinite(v) or not 0 <= v <= 1: raise ValueError('Thresholds must be in [0, 1]')
        if not 0 <= self.minimum_pitch <= self.maximum_pitch <= 127: raise ValueError('Invalid pitch range')
        if not 10 <= self.minimum_note_ms <= 2000: raise ValueError('Minimum note length must be 10–2000 ms')
        if not 1 <= self.max_seconds <= 3600: raise ValueError('Audio duration limit must be 1–3600s')


def model_status():
    from importlib.util import find_spec
    if find_spec('basic_pitch') is None or find_spec('onnxruntime') is None:
        return {'available':False,'message':'Run python tools/install_transcription.py in the application environment'}
    try:
        from basic_pitch import build_icassp_2022_model_path, FilenameSuffix
        path = build_icassp_2022_model_path(FilenameSuffix.onnx)
        return {'available':path.is_file(),'backend':'Basic Pitch 0.4.0 / ONNX','model_path':str(path)}
    except (ImportError,OSError) as e:
        return {'available':False,'message':str(e)}


def decode_audio(path, output, max_seconds=600):
    """Decode full input; reject over-limit inputs rather than silently truncating."""
    if not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg is required for audio/video decoding')
    path = Path(path)
    if not path.is_file(): raise FileNotFoundError(path)
    command = ['ffmpeg','-v','error','-nostdin','-y','-i',str(path),'-vn','-ac','1','-ar','22050',
               '-t',str(max_seconds+1),'-c:a','pcm_s16le',str(output)]
    result = subprocess.run(command,capture_output=True,text=True,timeout=900)
    if result.returncode: raise RuntimeError('Audio decode failed: '+result.stderr[-1000:])
    info = sf.info(output)
    if info.duration > max_seconds: raise ValueError(f'Input exceeds {max_seconds:g}s transcription limit')
    if info.duration < .05: raise ValueError('Audio input is empty or too short')
    return {'duration':info.duration,'sample_rate':info.samplerate,'channels':info.channels}


def _atomic_text(path, obj):
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def transcribe(path, directory, options=None, progress=None):
    options = options or TranscriptionOptions(); options.validate()
    status = model_status()
    if not status['available']: raise RuntimeError(status.get('message','ONNX model missing'))
    source = Path(path); directory = Path(directory); directory.mkdir(parents=True,exist_ok=True)
    def report(percent, message):
        if progress: progress(percent,message)
    digest = hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): digest.update(block)
    model_path = Path(status['model_path'])
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    key = hashlib.sha256(('tr1pp-onnx-pipeline-2'+digest.hexdigest()+model_hash+json.dumps(asdict(options),sort_keys=True)).encode()).hexdigest()
    out = directory/(key+'.mid'); metadata_path = directory/(key+'.json')
    if out.is_file() and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if hashlib.sha256(out.read_bytes()).hexdigest() == metadata.get('midi_sha256'):
            metadata.update(midi_path=str(out),cache_hit=True); report(100,'Loaded cached transcription'); return metadata
    report(5,'Decoding audio to mono 22.05 kHz')
    with tempfile.TemporaryDirectory() as tmp:
        decoded = Path(tmp)/'input.wav'; audio_info = decode_audio(source,decoded,options.max_seconds)
        # Reject silence before loading the model.
        samples, _ = sf.read(decoded,dtype='float32')
        if float(np.max(np.abs(samples))) < 1e-5: raise ValueError('Audio input is silent')
        report(20,'Running pretrained Basic Pitch ONNX model')
        from basic_pitch.inference import Model, predict
        _, _, events = predict(decoded,Model(model_path),onset_threshold=options.onset_threshold,
                               frame_threshold=options.frame_threshold,minimum_note_length=options.minimum_note_ms,
                               minimum_frequency=pretty_midi.note_number_to_hz(options.minimum_pitch),
                               maximum_frequency=pretty_midi.note_number_to_hz(options.maximum_pitch))
        report(85,'Filtering note activations and assigning hands')
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        tracks = [pretty_midi.Instrument(0,name='Left Hand'),pretty_midi.Instrument(0,name='Right Hand')] if options.split_hands else [pretty_midi.Instrument(0,name='Transcription')]
        notes = []
        seen = set()
        for start,end,pitch,activation,*_ in sorted(events,key=lambda e:(e[0],e[2])):
            start = max(0,float(start)); end = min(audio_info['duration'],float(end)); pitch=int(pitch); activation=float(activation)
            if not all(math.isfinite(x) for x in (start,end,activation)): continue
            if end-start < options.minimum_note_ms/1000 or activation < options.minimum_confidence: continue
            if not options.minimum_pitch <= pitch <= options.maximum_pitch: continue
            identity = (round(start,4),round(end,4),pitch)
            if identity in seen: continue
            seen.add(identity)
            hand = int(pitch >= 60) if options.split_hands else 0
            tracks[hand].notes.append(pretty_midi.Note(max(1,min(127,round(activation*127))),pitch,start,end))
            notes.append({'start':start,'end':end,'pitch':pitch,'activation':activation,'track':hand})
        if not notes: raise ValueError('Model detected no notes at the chosen thresholds; adjust settings or use source MIDI')
        nonempty = [i for i,track in enumerate(tracks) if track.notes]
        for note in notes:
            note['hand'] = 'right' if options.split_hands and note['track'] == 1 else 'left' if options.split_hands else 'unsplit'
            note['track'] = nonempty.index(note['track'])
        midi.instruments = [tracks[i] for i in nonempty]
        temp_midi = Path(tmp)/'result.mid'; midi.write(str(temp_midi))
        midi_bytes = temp_midi.read_bytes()
        # A rename from the temporary directory may cross filesystems; sibling write avoids that.
        fd, sibling = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(fd,'wb') as f: f.write(midi_bytes); f.flush(); os.fsync(f.fileno())
            os.replace(sibling,out)
        finally:
            if os.path.exists(sibling): os.unlink(sibling)
    metadata = dict(midi_path=str(out),source=str(source),source_sha256=digest.hexdigest(),
                    midi_sha256=hashlib.sha256(midi_bytes).hexdigest(),model_sha256=model_hash,
                    backend=status['backend'],options=asdict(options),audio=audio_info,notes=notes,
                    mean_activation=float(np.mean([n['activation'] for n in notes])),cache_hit=False,
                    message='Model activations are uncalibrated; review pitches, rhythm and hands in the editor.')
    _atomic_text(metadata_path,metadata); report(100,f'Transcribed {len(notes)} notes')
    return metadata
