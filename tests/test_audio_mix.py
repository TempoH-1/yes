import shutil
import numpy as np
import pretty_midi
import soundfile as sf
import pytest
from tr1pp.audio import mix_audio,render_mix,export_stems,waveform
from tr1pp.project import TrackMix

def midi():
    pm=pretty_midi.PrettyMIDI()
    for pitch in (60,72):
        ins=pretty_midi.Instrument(0);ins.notes=[pretty_midi.Note(100,pitch,.1,.8)];pm.instruments.append(ins)
    return pm

def test_mute_solo_pan_volume_and_automation_have_audible_effects():
    pm=midi()
    a=mix_audio(pm,[TrackMix(pan=-1),TrackMix(mute=True)],rate=8000)
    assert np.max(np.abs(a[:,0]))>.01 and np.max(np.abs(a[:,1]))<1e-7
    b=mix_audio(pm,[TrackMix(pan=-1,volume=.4),TrackMix(mute=True)],rate=8000)
    assert np.max(np.abs(b))==pytest.approx(np.max(np.abs(a))*.5)
    c=mix_audio(pm,[TrackMix(solo=True,pan=-1),TrackMix()],rate=8000)
    assert np.allclose(c,a)
    d=mix_audio(pm,[TrackMix(automation=[[0,0],[1,0]]),TrackMix(mute=True)],rate=8000)
    assert not np.any(d)

@pytest.mark.parametrize('extension',['wav','flac','mp3'])
def test_export_codecs_and_stems(tmp_path,extension):
    if extension=='mp3' and not shutil.which('ffmpeg'):pytest.skip('FFmpeg not installed')
    path=render_mix(midi(),tmp_path/f'mix.{extension}',rate=8000)
    audio,rate=sf.read(path)
    assert audio.ndim==2 and audio.shape[1]==2 and rate==8000
    assert np.max(np.abs(audio))>.01
    if extension=='wav':
        data=waveform(path,points=100);assert data['duration']>1 and len(data['peaks'])<=100
        stems=export_stems(midi(),tmp_path/'stems',rate=8000)
        assert len(stems)==2 and all(p.is_file() for p in stems)


def test_invalid_and_overlong_render_rejected():
    pm=midi()
    with pytest.raises(ValueError,match='limit'):mix_audio(pm,max_seconds=.1)
    with pytest.raises(ValueError,match='Mismatch|mismatch'):mix_audio(pm,[])


def test_track_effects_change_signal_and_create_real_tail():
    pm=midi()
    dry=mix_audio(pm,[TrackMix(),TrackMix(mute=True)],rate=8000)
    delay=mix_audio(pm,[TrackMix(effects={'delay_mix':.5,'delay_seconds':.3}),TrackMix(mute=True)],rate=8000)
    assert len(delay)>len(dry)
    assert np.max(np.abs(delay[int(1.1*8000):]))>.001
    filtered=mix_audio(pm,[TrackMix(effects={'lowpass_hz':100}),TrackMix(mute=True)],rate=8000)
    assert np.sqrt(np.mean(filtered**2))<np.sqrt(np.mean(dry**2))*.5
    room=mix_audio(pm,[TrackMix(effects={'reverb_mix':.4}),TrackMix(mute=True)],rate=8000)
    assert len(room)>len(dry) and np.max(np.abs(room[int(1.1*8000):]))>.0001
