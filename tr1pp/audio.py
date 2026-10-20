"""Shared stereo preview/export renderer with real track mixing and gain automation."""
from __future__ import annotations
from pathlib import Path
import math
import shutil
import subprocess
import tempfile
import numpy as np
import soundfile as sf
from .project import TrackMix


def _synthetic(instrument, frames, rate):
    out = np.zeros(frames, dtype=np.float32)
    for n in instrument.notes:
        start = max(0, int(n.start*rate)); stop = min(frames, int((n.end+.08)*rate))
        if stop <= start: continue
        t = np.arange(stop-start, dtype=np.float32)/rate
        gate = np.minimum(1, t/.008)*np.minimum(1, np.maximum(0, n.end-n.start+.08-t)/.08)
        hz = 440*2**((n.pitch-69)/12)
        signal = np.sin(2*np.pi*hz*t) + .25*np.sin(4*np.pi*hz*t) + .08*np.sin(6*np.pi*hz*t)
        out[start:stop] += (n.velocity/127)*.14*signal*gate*np.exp(-1.1*t)
    return out


def _apply_effects(mono,rate,effects):
    """Offline low-pass, three-tap delay and deterministic convolution ambience."""
    from scipy.signal import butter,sosfilt,fftconvolve
    result=mono
    cutoff=effects.get('lowpass_hz',0)
    if cutoff:
        cutoff=min(rate*.49,max(20,cutoff))
        result=sosfilt(butter(2,cutoff,fs=rate,output='sos'),result).astype(np.float32)
    wet=effects.get('delay_mix',0)
    if wet:
        dry=result.copy();result=result.copy();offset=max(1,int(effects.get('delay_seconds',.25)*rate))
        for index in range(1,4):
            shift=offset*index
            if shift<len(result):result[shift:]+=dry[:-shift]*wet*(.5**(index-1))
    wet=effects.get('reverb_mix',0)
    if wet:
        # Small reproducible artificial room response, not a concert-piano model.
        time=np.arange(int(rate*1.2),dtype=np.float32)/rate
        impulse=np.random.default_rng(17).standard_normal(len(time)).astype(np.float32)*np.exp(-time/.22)
        impulse[:int(rate*.012)]=0
        norm=float(np.sqrt(np.sum(impulse*impulse)))
        if norm:impulse/=norm
        ambience=fftconvolve(result,impulse,mode='full')[:len(result)]
        result=result*(1-wet)+ambience*wet
    return result


def mix_audio(midi, mixer=None, *, rate=22050, soundfont=None, max_seconds=600):
    if rate < 8000 or rate > 96000: raise ValueError('Sample rate must be 8000–96000 Hz')
    effects_list=[m.effects for m in mixer] if mixer is not None else []
    tail=max([.5]+[e.get('delay_seconds',.25)*3 if e.get('delay_mix',0) else 0 for e in effects_list]+[1.2 if e.get('reverb_mix',0) else 0 for e in effects_list])
    duration = midi.get_end_time()+tail
    if midi.get_end_time() <= 0: raise ValueError('No MIDI events to render')
    if duration > max_seconds: raise ValueError(f'Render exceeds {max_seconds:g}s limit; select a smaller passage')
    if sum(len(i.notes) for i in midi.instruments) > 100000: raise ValueError('Render note limit exceeded')
    frames = int(duration*rate)+1
    mixer = list(mixer) if mixer is not None else [TrackMix() for _ in midi.instruments]
    if len(mixer) != len(midi.instruments): raise ValueError('Mixer/track count mismatch')
    for mix in mixer: mix.validate()
    use_solo = any(m.solo for m in mixer)
    output = np.zeros((frames, 2), dtype=np.float32)
    if soundfont and not Path(soundfont).is_file(): raise FileNotFoundError(soundfont)
    for ins, mix in zip(midi.instruments, mixer):
        if mix.mute or (use_solo and not mix.solo): continue
        if soundfont:
            # pretty_midi's instrument renderer respects CC64 and pitch bend.
            try: mono = ins.fluidsynth(fs=rate, sf2_path=str(soundfont))
            except (ImportError, OSError) as e: raise RuntimeError('FluidSynth native library is required') from e
            mono = np.asarray(mono[:frames], dtype=np.float32)
        else:
            if ins.is_drum: continue  # Synthetic pitched preview has no drum kit.
            mono = _synthetic(ins, frames, rate)
        if len(mono)<frames:mono=np.pad(mono,(0,frames-len(mono)))
        mono=_apply_effects(mono[:frames],rate,mix.effects)
        size = min(frames, len(mono))
        if mix.automation:
            t = np.arange(size, dtype=np.float64)/rate
            points = np.asarray(mix.automation)
            mono = mono[:size]*np.interp(t, points[:,0], points[:,1])
        angle = (mix.pan+1)*np.pi/4
        output[:size,0] += mono[:size]*mix.volume*math.cos(angle)
        output[:size,1] += mono[:size]*mix.volume*math.sin(angle)
    peak = float(np.max(np.abs(output)))
    # Fixed master limiter: no per-track normalization that would undo mixer faders.
    if peak > .98: output *= .98/peak
    return output


def render_mix(midi, path, mixer=None, soundfont=None, rate=22050):
    path = Path(path)
    if path.suffix.lower() not in ('.wav','.flac','.mp3'): raise ValueError('Choose WAV, FLAC or MP3')
    audio = mix_audio(midi, mixer, rate=rate, soundfont=soundfont)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == '.mp3':
        if not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg is required for MP3')
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp)/'mix.wav'; sf.write(wav, audio, rate, subtype='PCM_24')
            result = subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(wav),'-q:a','2',str(path)],
                                    capture_output=True, text=True, timeout=900)
            if result.returncode: raise RuntimeError(result.stderr[-1000:])
    else: sf.write(path, audio, rate, subtype='PCM_24')
    return path


def waveform(path, points=1200):
    """Bounded peak envelope, streaming without loading a full media file."""
    with sf.SoundFile(path) as f:
        duration = len(f)/f.samplerate
        block = max(1, math.ceil(len(f)/points))
        peaks = []
        for chunk in f.blocks(blocksize=block, dtype='float32'):
            peaks.append(float(np.max(np.abs(chunk))) if len(chunk) else 0.)
    return {'duration': duration, 'peaks': peaks}


def export_stems(midi, directory, mixer=None, soundfont=None, rate=22050):
    import copy, pretty_midi
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    mixes = mixer or [TrackMix() for _ in midi.instruments]
    paths = []
    for index, ins in enumerate(midi.instruments):
        stem = copy.deepcopy(midi); stem.instruments = [copy.deepcopy(ins)]
        mix = copy.deepcopy(mixes[index]); mix.solo = False
        path = directory/f'{index+1:02d}-track.wav'
        render_mix(stem, path, [mix], soundfont, rate); paths.append(path)
    return paths
