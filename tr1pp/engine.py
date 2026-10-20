"""MIDI-first, motif-preserving arrangement engine. No audio-to-MIDI promises."""
from __future__ import annotations
import copy, json, math, random
from dataclasses import dataclass, asdict
from pathlib import Path
import pretty_midi
import numpy as np
from .music_theory import phrase_windows, motif_signatures
from .quality_metrics import candidate_score

PC_NAMES=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
MAJOR=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
MINOR=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

@dataclass
class Settings:
    mode:str='Seamless Transition'
    bridge_bars:int=8
    crossfade_bars:int=4
    target_bpm:float=0
    lead_in_bars:int=4
    motif_strength:float=.55
    humanize_ms:float=7
    difficulty:int=65
    max_notes_per_second:int=24
    strict_two_hands:bool=True
    seed:int=17
    original_preservation:float=1.0


def load(path):
    from .midi_repair import recover_midi
    midi, repairs=recover_midi(path)
    midi.tr1pp_repairs=repairs
    if not any(i.notes and not i.is_drum for i in midi.instruments):
        raise ValueError('No pitched MIDI notes found. Audio must first be accurately transcribed to MIDI.')
    return midi

def all_notes(pm):
    return sorted((n for i in pm.instruments if not i.is_drum for n in i.notes),key=lambda n:n.start)

def key_estimate(pm):
    pc=np.zeros(12)
    for n in all_notes(pm): pc[n.pitch%12]+=max(.02,n.end-n.start)*max(1,n.velocity)
    if not pc.sum():return 'Unknown',0,False
    v=pc/pc.sum()
    cand=[]
    for root in range(12):
        for mi,prof in ((False,MAJOR),(True,MINOR)):
            score=float(np.corrcoef(v,np.roll(prof,root))[0,1])
            cand.append((score,root,mi))
    score,root,mi=max(cand)
    return PC_NAMES[root]+(' minor' if mi else ' major'),root,mi

def analyse(pm):
    notes=all_notes(pm); dur=max(n.end for n in notes)
    key,root,minor=key_estimate(pm)
    try:bpm=float(pm.estimate_tempo())
    except Exception:bpm=120.
    if not np.isfinite(bpm) or bpm<35 or bpm>300:bpm=120.
    hist=np.bincount([n.pitch for n in notes],minlength=128)
    melody=[n for n in notes if n.pitch>=max(60,int(np.percentile([x.pitch for x in notes],55)))]
    beats=[]
    for n in melody:
        if not beats or n.start-beats[-1].start>.065:beats.append(n)
    counts=np.histogram([n.start for n in notes],bins=max(1,int(math.ceil(dur/4))))[0]
    instruments=[{'name':i.name or ('Drums' if i.is_drum else pretty_midi.program_to_instrument_name(i.program)), 'notes':len(i.notes)} for i in pm.instruments]
    boundaries=phrase_windows(notes,dur)
    motifs=motif_signatures(notes)
    return {'phrase_boundary_candidates':boundaries,'repeated_interval_motifs':motifs,'midi_repairs':getattr(pm,'tr1pp_repairs',[]),'duration':round(dur,2),'notes':len(notes),'bpm_estimate':round(bpm,2),'key_estimate':key,
        'range':[min(n.pitch for n in notes),max(n.pitch for n in notes)],
        'peak_note_count_per_4sec':int(max(counts)),'melody_candidates':len(beats),
        'instruments':instruments,'confidence':'Heuristic, not confirmed transcription',
        'limitations':'Key/melody estimates are pitch-statistical; tempo changes and exact hands are not reliably inferred.'}

def _copy_note(n,start=None,end=None,velocity=None,pitch=None):
    return pretty_midi.Note(int(np.clip(n.velocity if velocity is None else velocity,1,127)),
      int(np.clip(n.pitch if pitch is None else pitch,0,127)),
      max(0,float(n.start if start is None else start)),
      max(.001,float(n.end if end is None else end)))

def _append_segment(out, pm, src_start,src_end,dst_start,ratio=1.,gain=1.,fade=None, channel=None):
    for ins in pm.instruments:
        if ins.is_drum:continue
        dest=out[0] if channel is None else out[channel]
        for n in ins.notes:
            if n.start>=src_end or n.end<=src_start:continue
            s=max(src_start,n.start);e=min(src_end,n.end)
            ns=dst_start+(s-src_start)*ratio;ne=dst_start+(e-src_start)*ratio
            weight=1.
            if fade:
                t=(s-src_start)/max(.001,src_end-src_start)
                weight=(t if fade=='in' else 1-t)*.75+.25
            dest.notes.append(_copy_note(n,ns,ne,max(1,int(n.velocity*gain*weight))))

def _motif(pm, length=4., high=True):
    notes=all_notes(pm)
    if not notes:return []
    # Favor a relatively early, recognizable high-register passage, preserve source pitch contour.
    start=next((n.start for n in notes if n.pitch>=60),notes[0].start)
    xs=[n for n in notes if start<=n.start<start+length]
    if high:
        cutoff=np.percentile([n.pitch for n in xs],55) if xs else 60
        xs=[n for n in xs if n.pitch>=cutoff]
    return xs[:40]

def _nearest_scale(pitch,root,minor):
    allowed={0,2,3,5,7,8,10} if minor else {0,2,4,5,7,9,11}
    return min(range(max(24,pitch-3),min(108,pitch+4)),key=lambda p:abs(pitch-p)+(0 if (p-root)%12 in allowed else 6))

def _transpose_mod(note,root_from,root_to):
    interval=(root_to-root_from+6)%12-6
    return max(24,min(108,note+interval))

def _separate_hands(pm,strict=True):
    right=pretty_midi.Instrument(0,name='Right Hand')
    left=pretty_midi.Instrument(0,name='Left Hand')
    active={0:[],1:[]}
    drops=0
    for n in all_notes(pm):
        hand=1 if n.pitch>=60 else 0
        dst=(left,right)[hand]
        if strict:
            # Maintain only currently sounding notes, avoiding O(N^2) rescans.
            running=[x for x in active[hand] if x.end>n.start+.015]
            active[hand]=running
            if len(running)>=4 or (running and
                max([x.pitch for x in running]+[n.pitch])-min([x.pitch for x in running]+[n.pitch])>17):
                drops+=1;continue
            active[hand].append(n)
        dst.notes.append(copy.deepcopy(n))
    return [left,right],drops

def _humanize(insts,ms,seed):
    rng=random.Random(seed)
    if not ms:return
    for ins in insts:
        for n in ins.notes:
            jitter=rng.uniform(-ms,ms)/1000.
            n.start=max(0,n.start+jitter)
            n.end=max(n.start+.04,n.end+jitter)
            n.velocity=int(np.clip(n.velocity+rng.randint(-5,5),15,127))

def _quality(pm,bridge_start,bridge_end,strict_drops):
    notes=all_notes(pm);duration=max(n.end for n in notes)
    density=max(np.histogram([n.start for n in notes],bins=max(1,int(duration)+1))[0])
    glitches=sum(1 for n in notes if n.end<=n.start)
    return {'note_count':len(notes),'duration_sec':round(duration,2),'maximum_notes_in_one_second':int(density),
       'invalid_note_lengths':glitches,'notes_reduced_by_playability_filter':strict_drops,
       'bridge_sec':[round(bridge_start,2),round(bridge_end,2)],
       'flags':(['Very high peak density; review piano playability'] if density>35 else [])+
       (['Large number of removed notes; review harmony and voice leading'] if strict_drops>150 else []),
       'caution':'Automated checks cannot judge musical beauty, melodic authenticity, or pianist feasibility.'}

def _boundary_motif(pm, seconds, tail=False):
    """Find source-native high-register note candidates near a phrase boundary."""
    notes=all_notes(pm)
    if not notes:return []
    end=max(n.end for n in notes)
    if tail:
        # Prefer material ending at a nearby detected phrase boundary; fallback to song ending.
        candidates=phrase_windows(notes,end)
        boundary=next((x['time'] for x in candidates if end-seconds*1.8<x['time']<end-.15),end)
        start=max(0,boundary-seconds)
        selection=[n for n in notes if start<=n.start<boundary]
    else:
        start=0
        candidates=phrase_windows(notes,end)
        boundary=next((x['time'] for x in candidates if .6<x['time']<seconds*1.8),seconds)
        selection=[n for n in notes if start<=n.start<boundary]
    if not selection:
        start=max(0,end-seconds) if tail else 0
        selection=[n for n in notes if start<=n.start<(end if tail else seconds)]
    if not selection:return []
    threshold=max(55,float(np.percentile([n.pitch for n in selection],55)))
    melody=[n for n in selection if n.pitch>=threshold]
    # Convert to offsets at origin. Remove simultaneous doubling in same key.
    origin=min(n.start for n in melody) if melody else start
    return [(n.start-origin,max(.09,n.end-n.start),n.pitch,n.velocity) for n in melody[:100]]

def _make_bridge(a,b,start,duration,bpm,root_a,root_b,mode,variant):
    """Compose and rate one short bridge using actual source motifs and a tonal pivot.
    Candidates vary arrival strategy; no random-note filler. All named styles
    retain their source motifs; only Jazz/Ragtime/Virtuoso apply embellishments.
    """
    instrument=pretty_midi.Instrument(0,name='Composed bridge')
    left=_boundary_motif(a,min(8,duration*.65),tail=True)
    right=_boundary_motif(b,min(8,duration*.65),tail=False)
    if not left or not right:return instrument,{'rating':-1,'candidate':variant}
    beat=60/bpm
    split=[.43,.51,.59][variant]
    mid=start+duration*split
    shift=(root_a-root_b+6)%12-6
    # Melodic anticipation: upcoming motif first in prior key, then untransposed on arrival.
    def copy(motif,at,max_duration,transpose=0,volume=.8,scale=1):
        for offset,d,p,v in motif:
            when=at+offset*scale
            if when>=at+max_duration:continue
            stop=min(at+max_duration,when+max(.07,d*scale))
            instrument.notes.append(pretty_midi.Note(max(20,min(127,int(v*volume))),max(21,min(108,p+transpose)),when,stop))
    copy(left,start,duration*split,volume=.75,scale=.85)
    copy(right,start+duration*.28,duration*.18,transpose=shift,volume=.36,scale=.65)
    copy(right,mid,duration*(1-split),volume=.87,scale=.82)
    # Bridge bass uses authentic nearby roots and moves via fifth, if useful.
    root_step=(root_b-root_a+6)%12-6
    fifth=(root_a+7)%12
    pulses=max(4,int(duration/beat))
    for j in range(pulses):
        t=start+j*duration/pulses
        frac=j/pulses
        base=root_a if frac<.35 else fifth if frac<.67 else root_b
        pitch=36+base
        # Variant chooses register and accented attack, not a random chord.
        if mode=='Ragtime' and j%2==1:pitch+=12
        velocity=48+int(25*frac)
        instrument.notes.append(pretty_midi.Note(velocity,pitch,t,min(start+duration,t+duration/pulses*.82)))
    # Controlled embellishment only in requested demanding styles.
    if mode in ('Virtuoso Piano','Jazz Fusion'):
        end_of_a=start+duration*.4
        for j in range(4):
            pp=60+root_a+([0,2,4,7][j])
            st=end_of_a+j*beat*.22
            if st<mid:instrument.notes.append(pretty_midi.Note(56,pp,st,min(mid,st+beat*.18)))
    # Transparent score criteria, not musical quality proof.
    transition_notes=[n for n in instrument.notes if mid<=n.start<mid+beat]
    anchoring=sum(1 for n in transition_notes if (n.pitch-root_b)%12 in (0,3,4,7))
    cross_hits=sum(1 for n in instrument.notes if n.start<mid and (n.pitch-root_b)%12 in (0,3,4,7))
    density=len(instrument.notes)/max(.1,duration)
    metrics=candidate_score(instrument.notes,start,start+duration,anchoring)
    rating=metrics['objective_proxy_score']+cross_hits*.15-max(0,density-16)*2-abs(root_step)*.04
    return instrument,{'candidate':variant,'tonal_anchor_notes':anchoring,'prearrival_anchor_notes':cross_hits,'bridge_density_nps':round(density,2),'heuristic_rating':round(rating,2),'technical_diagnostics':metrics}

def arrange(paths,settings=None):
    settings=settings or Settings()
    if len(paths)<2:raise ValueError('Import at least two MIDI files')
    sources=[load(p) for p in paths]
    out=pretty_midi.PrettyMIDI(initial_tempo=120)
    merged=pretty_midi.Instrument(0,name='Arrangement')
    bridge_segments=[]; cursor=0.; reports=[]; source_regions=[]
    for idx,src in enumerate(sources):
        info=analyse(src);reports.append(info)
        duration=max(n.end for n in all_notes(src))  # Never round source duration when copying notes.
        # Preserve original source music except for a short overlap at the boundary.
        if idx==0:
            _append_segment([merged],src,0,duration,0)
            cursor=duration
            source_regions.append({'source_index':idx,'start':0.,'end':duration})
            continue
        prev=sources[idx-1];previous=reports[idx-1]
        bpm=max(45,min(240,settings.target_bpm or (previous['bpm_estimate']+info['bpm_estimate'])/2))
        bar=4*60/bpm
        overlap=min(cursor*.2,settings.crossfade_bars*bar, duration*.18)
        bridge=max(bar*2,settings.bridge_bars*bar)
        start=max(0,cursor-overlap)
        # Respect first piece's ending; bridge explicitly composes new connective material.
        # Start following song after bridge and keep its complete recognizable opening intact.
        bridge_start=cursor;bridge_end=cursor+bridge
        _,r1,mi1=key_estimate(prev);_,r2,mi2=key_estimate(src)
        candidates=[_make_bridge(prev,src,bridge_start,bridge,bpm,r1,r2,settings.mode,k) for k in range(3)]
        bridge_ins,selection=max(candidates,key=lambda item:item[1].get('heuristic_rating',-999))
        selection['compared']=[dict(score) for _,score in candidates]
        merged.notes.extend(bridge_ins.notes)
        _append_segment([merged],src,0,duration,bridge_end)
        bridge_segments.append({'after_song':idx,'start':round(bridge_start,3),'end':round(bridge_end,3),'first_root':PC_NAMES[r1],'next_root':PC_NAMES[r2],'candidate_evaluation':selection})
        source_regions.append({'source_index':idx,'start':bridge_end,'end':bridge_end+duration})
        cursor=bridge_end+duration
    # Separate after arrangement so that motif notes and all source notes remain available.
    tracks,drops=_separate_hands(pretty_midi.PrettyMIDI(),False) if False else _separate_hands(_pack(merged),settings.strict_two_hands)
    _humanize(tracks,settings.humanize_ms,settings.seed)
    # Sustain CC using phrase-scaled pulses rather than 100% pedal throughout.
    for ins in tracks:
        end=max((n.end for n in ins.notes),default=0)
        t=0.
        while t<end:
            ins.control_changes.append(pretty_midi.ControlChange(64,90,t))
            ins.control_changes.append(pretty_midi.ControlChange(64,0,min(end,t+1.6)))
            t+=2.
        out.instruments.append(ins)
    quality=_quality(out,bridge_segments[0]['start'] if bridge_segments else 0,bridge_segments[-1]['end'] if bridge_segments else 0,drops)
    return out,{'sources':reports,'source_regions':source_regions,'transitions':bridge_segments,'settings':asdict(settings),'quality':quality,
        'implementation':'Source-derived boundary motif bridge with three scored candidates and sequential arrangement. Original note timings retained except edge clipping and optional humanization.',
        'limits':['No automatic audio transcription','No generative composition model','Heuristic piano-hand division; not a guarantee of two-hand playability','No local tempo ramps yet; no reliable style synthesis beyond small bass/ornament differences','MIDI velocities and pedal are approximate']}

def _pack(inst):
    x=pretty_midi.PrettyMIDI();x.instruments=[inst];return x

def render_audio(pm,out_path,soundfont=None,rate=22050):
    if not soundfont or not Path(soundfont).is_file():
        raise RuntimeError('Select an SF2 SoundFont to render audio; MIDI contains notes, not samples.')
    try:audio=pm.fluidsynth(fs=rate,sf2_path=str(soundfont))
    except (ImportError,OSError) as e:raise RuntimeError('FluidSynth native DLL and pyfluidsynth are required for audio rendering: '+str(e)) from e
    import soundfile as sf
    import shutil, subprocess, tempfile
    out=Path(out_path)
    if out.suffix.lower() not in ('.wav','.flac','.mp3'):raise ValueError('Supported audio exports: WAV, FLAC, MP3')
    if out.suffix.lower()!='.mp3':sf.write(str(out),audio,rate);return out
    if not shutil.which('ffmpeg'):raise RuntimeError('FFmpeg is required for MP3 export')
    with tempfile.TemporaryDirectory() as tmp:
        wav=Path(tmp)/'render.wav';sf.write(str(wav),audio,rate)
        process=subprocess.run(['ffmpeg','-nostdin','-y','-i',str(wav),'-codec:a','libmp3lame','-qscale:a','2',str(out)],capture_output=True,text=True,timeout=900)
        if process.returncode:raise RuntimeError('FFmpeg MP3 encoding failed: '+process.stderr[-600:])
    return out

def export_musicxml(pm,path):
    """Optional MIDI to MusicXML converter; transcription quantisation is approximate."""
    try:
        from music21 import converter
    except ImportError as e:raise RuntimeError('Install music21 to use MusicXML export: pip install music21') from e
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        midi_path=Path(tmp)/'arrangement.mid';pm.write(str(midi_path))
        score=converter.parse(str(midi_path),quantizePost=True)
        score.write('musicxml',fp=str(path))
    return Path(path)

def inspect_audio(path):
    import librosa
    y,sr=librosa.load(str(path),sr=22050,mono=True,duration=240)
    tempo,_=librosa.beat.beat_track(y=y,sr=sr)
    chroma=librosa.feature.chroma_stft(y=y,sr=sr)
    return {'file':str(path),'analysed_seconds':round(len(y)/sr,2),'estimated_bpm':float(np.asarray(tempo).flat[0]),
       'chroma':np.round(np.mean(chroma,axis=1),3).tolist(),
       'note':'Analysis metadata only. This does not yield reliable polyphonic MIDI or isolated melodies.'}
