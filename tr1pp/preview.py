"""Dependency-light, explicitly synthetic audio preview of MIDI notes.
Not an acoustic piano emulator; uses a decaying sine-based signal for edit audition.
"""
from pathlib import Path
import numpy as np
import soundfile as sf

def render_preview(pm,path,sample_rate=16000,max_seconds=240):
    notes=[n for ins in pm.instruments if not ins.is_drum for n in ins.notes]
    if not notes:raise ValueError('Cannot preview MIDI with no pitched notes')
    duration=min(max(n.end for n in notes)+.25,max_seconds)
    if duration<=0:raise ValueError('Invalid duration')
    output=np.zeros(int(duration*sample_rate)+1,dtype=np.float32)
    # Intentional cap avoids memory blowups when previewing dense virtuoso files.
    if len(notes)>60000:raise ValueError('Preview exceeds the 60,000-note limit; export MIDI instead')
    for n in notes:
        s=max(0,int(n.start*sample_rate));e=min(len(output),int(n.end*sample_rate))
        if e<=s:continue
        t=np.arange(e-s,dtype=np.float32)/sample_rate
        hz=440*2**((n.pitch-69)/12)
        env=np.minimum(1,t/.009)*np.exp(-1.3*t)
        output[s:e]+=((n.velocity/127)*.11*np.sin(2*np.pi*hz*t)*env).astype(np.float32)
    peak=float(np.max(np.abs(output)))
    if peak>.95:output*=.95/peak
    sf.write(str(path),output,sample_rate)
    return Path(path)
