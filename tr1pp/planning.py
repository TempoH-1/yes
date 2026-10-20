"""Explicit source-derived arrangement plans, not a generative composition model.

Clips are independently editable source excerpts in a shared beat timeline.
Tempo adaptation uses the source's initial MIDI tempo, including original local
rubato in the excerpt. Harmonic alignment is an optional global transposition,
not a guarantee of compatible chords during layering.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import copy
import math
import pretty_midi
from .engine import load, key_estimate, analyse

@dataclass
class Clip:
    source: int
    source_start: float
    source_end: float
    at_beat: float
    transpose: int = 0
    gain: float = 1.
    repeats: int = 1
    label: str = ''

@dataclass
class ArrangementPlan:
    bpm: float = 120.
    difficulty: int = 100
    clips: list[Clip] = field(default_factory=list)
    title: str = 'Custom arrangement'

    def validate(self, count):
        if not math.isfinite(self.bpm) or not 20 <= self.bpm <= 300: raise ValueError('Plan tempo must be 20–300 BPM')
        if not isinstance(self.difficulty,int) or not 0 <= self.difficulty <= 100: raise ValueError('Difficulty must be 0–100')
        if not self.clips or len(self.clips)>256: raise ValueError('Plan must contain 1–256 clips')
        for c in self.clips:
            if not isinstance(c.source,int) or not 0 <= c.source < count: raise ValueError('Plan source index is out of range')
            if not all(math.isfinite(x) for x in (c.source_start,c.source_end,c.at_beat,c.gain)): raise ValueError('Clip values must be finite')
            if c.source_start < 0 or c.source_end <= c.source_start or c.at_beat < 0: raise ValueError('Invalid clip range or position')
            if not isinstance(c.repeats,int) or not 1 <= c.repeats <= 16: raise ValueError('Clip repeat count must be 1–16')
            if not isinstance(c.transpose,int) or not -48 <= c.transpose <= 48: raise ValueError('Clip transposition must be within four octaves')
            if not 0 <= c.gain <= 2: raise ValueError('Clip gain must be 0–2')

    @classmethod
    def from_dict(cls, data):
        data=dict(data);data['clips']=[Clip(**c) for c in data.get('clips',[])];return cls(**data)


def preset_plan(paths, preset='A/B/A thematic', bpm=120, difficulty=65, bars=8, align_keys=True):
    sources=[load(p) for p in paths]
    if len(sources)<2: raise ValueError('At least two MIDI sources are required')
    target_root=key_estimate(sources[0])[1]
    excerpts=[]
    for index,source in enumerate(sources):
        source_bpm=float(source.get_tempo_changes()[1][0])
        end=min(source.get_end_time(),bars*4*60/source_bpm)
        root=key_estimate(source)[1]
        transpose=(target_root-root+6)%12-6 if align_keys else 0
        beats=end*source_bpm/60
        excerpts.append((index,end,beats,transpose))
    clips=[];cursor=0.
    if preset=='Layered motifs':
        for index,end,beats,shift in excerpts:
            clips.append(Clip(index,0,end,0,shift,.7 if index else 1.,label=f'Layer {index+1}'))
    elif preset=='Call and response':
        # Alternate short source phrases, retaining each source's timing contour.
        for phrase in range(4):
            for index,end,beats,shift in excerpts:
                source_bpm=float(sources[index].get_tempo_changes()[1][0])
                length=min(end,4*60/source_bpm)
                origin=min(phrase*length,max(0,end-length))
                clips.append(Clip(index,origin,origin+length,cursor,shift,label=f'Response {phrase+1}.{index+1}'))
                cursor+=length*source_bpm/60
    else:
        order=list(range(len(excerpts)))+[0]
        for section,index in enumerate(order):
            _,end,beats,shift=excerpts[index]
            clips.append(Clip(index,0,end,cursor,shift,label='Reprise' if section==len(order)-1 else f'Theme {index+1}'))
            cursor+=beats
    return ArrangementPlan(bpm=bpm,difficulty=difficulty,clips=clips,title=preset)


def _simplify(notes, difficulty):
    if difficulty>=100:return notes,0
    max_poly=2+int(difficulty/20);min_gap=.045+(100-difficulty)*.0015
    groups=[]
    for n in sorted(notes,key=lambda n:(n.start,n.pitch)):
        if not groups or n.start-groups[-1][0].start>.025:groups.append([n])
        else:groups[-1].append(n)
    kept=[];last=-10.;active=[]
    for group in groups:
        onset=group[0].start
        # Preserve outer voices before inner chord tones. Deterministic reduction.
        ordered=sorted(group,key=lambda n:n.pitch)
        priority=[ordered[-1]]+([ordered[0]] if len(ordered)>1 else [])+ordered[1:-1]
        if onset-last<min_gap:continue
        active=[n for n in active if n.end>onset+.015]
        for note in priority:
            if len(active)>=max_poly:break
            kept.append(note);active.append(note)
        last=onset
    return sorted(kept,key=lambda n:(n.start,n.pitch)),len(notes)-len(kept)


def render_plan(paths, plan: ArrangementPlan):
    plan.validate(len(paths));sources=[load(p) for p in paths]
    out=pretty_midi.PrettyMIDI(initial_tempo=plan.bpm);regions=[];dropped=0
    for clip_index,clip in enumerate(plan.clips):
        source=sources[clip.source]
        if clip.source_end>source.get_end_time()+.001: raise ValueError(f'Clip {clip_index+1} ends after its source')
        source_bpm=float(source.get_tempo_changes()[1][0]);ratio=source_bpm/plan.bpm
        length=(clip.source_end-clip.source_start)*ratio
        offset=clip.at_beat*60/plan.bpm
        if offset+length*clip.repeats>600: raise ValueError('Arrangement plan exceeds ten-minute render limit')
        for source_track in source.instruments:
            target=pretty_midi.Instrument(source_track.program,is_drum=source_track.is_drum,
                                          name=f'{clip.label or "Clip "+str(clip_index+1)} / {source_track.name or "Piano"}')
            for repetition in range(clip.repeats):
                at=offset+repetition*length
                for note in source_track.notes:
                    if note.start>=clip.source_end or note.end<=clip.source_start:continue
                    start=at+(max(clip.source_start,note.start)-clip.source_start)*ratio
                    end=at+(min(clip.source_end,note.end)-clip.source_start)*ratio
                    pitch=note.pitch+(0 if source_track.is_drum else clip.transpose)
                    if 0<=pitch<=127 and end>start:
                        target.notes.append(pretty_midi.Note(max(1,min(127,round(note.velocity*clip.gain))),pitch,start,end))
                # Restore controller state at an excerpt boundary (including pedal).
                initial={}
                for event in sorted(source_track.control_changes,key=lambda e:e.time):
                    if event.time<clip.source_start:initial[event.number]=event.value
                    elif event.time<clip.source_end:
                        target.control_changes.append(pretty_midi.ControlChange(event.number,event.value,at+(event.time-clip.source_start)*ratio))
                for number,value in initial.items():target.control_changes.append(pretty_midi.ControlChange(number,value,at))
                bend=0
                for event in sorted(source_track.pitch_bends,key=lambda e:e.time):
                    if event.time<clip.source_start:bend=event.pitch
                    elif event.time<clip.source_end:target.pitch_bends.append(pretty_midi.PitchBend(event.pitch,at+(event.time-clip.source_start)*ratio))
                if bend:target.pitch_bends.append(pretty_midi.PitchBend(bend,at))
                target.control_changes.append(pretty_midi.ControlChange(64,0,at+length))
            if not target.notes:continue
            if not source_track.is_drum:target.notes,reduced=_simplify(target.notes,plan.difficulty);dropped+=reduced
            target.control_changes.sort(key=lambda e:e.time);target.pitch_bends.sort(key=lambda e:e.time)
            out.instruments.append(target)
        regions.append({'source_index':clip.source,'start':offset,'end':offset+length*clip.repeats,'label':clip.label,'transpose':clip.transpose})
    if not any(i.notes for i in out.instruments):raise ValueError('Plan produced no playable notes')
    report={'plan':asdict(plan),'sources':[analyse(p) for p in sources],'source_regions':regions,'transitions':[],
            'quality':{'note_count':sum(len(i.notes) for i in out.instruments),'duration_sec':out.get_end_time(),
                       'notes_reduced_by_difficulty':dropped,'invalid_note_lengths':0},
            'implementation':'Explicit source-excerpt sequencing/layering with tempo adaptation and optional global key transposition.',
            'limits':['Heuristic source-derived planning, not neural composition','Layered global keys do not ensure compatible local chords','Difficulty filter removes notes; inspect the result','Source local tempo variations are scaled uniformly']}
    return out,report


def harmonic_timeline(midi, window_beats=4):
    """Duration/velocity-weighted triad labels per bar with inspectable confidence."""
    bpm=float(midi.get_tempo_changes()[1][0]);window=window_beats*60/bpm
    if window<=0:raise ValueError('Harmonic window must be positive')
    notes=[n for i in midi.instruments if not i.is_drum for n in i.notes]
    labels=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
    result=[]
    for index in range(math.ceil(midi.get_end_time()/window)):
        start=index*window;end=start+window;weights=[0.]*12
        for n in notes:
            overlap=max(0,min(end,n.end)-max(start,n.start))
            if overlap:weights[n.pitch%12]+=overlap*n.velocity
        total=sum(weights)
        if not total:result.append({'start':start,'end':end,'chord':'Rest','coverage':0.});continue
        candidates=[]
        for root in range(12):
            for quality,intervals in [('major',(0,4,7)),('minor',(0,3,7)),('dim',(0,3,6)),('sus4',(0,5,7))]:
                coverage=sum(weights[(root+i)%12] for i in intervals)/total
                # Root support resolves otherwise equivalent subset matches.
                score=coverage+.05*weights[root]/total
                candidates.append((score,root,quality,coverage))
        _,root,quality,coverage=max(candidates)
        result.append({'start':round(start,4),'end':round(end,4),'chord':labels[root]+' '+quality,'coverage':round(coverage,3)})
    return result
