from pathlib import Path
import tempfile
import pytest
import pretty_midi
from tr1pp.engine import load,arrange,Settings
from tr1pp.midi_repair import repair_bytes,MIDIRepairError
from tr1pp.imports import validate_url

def synth(path,pitch):
    pm=pretty_midi.PrettyMIDI(initial_tempo=120)
    track=pretty_midi.Instrument(0)
    for i in range(32):track.notes.append(pretty_midi.Note(92,pitch+i%4,i*.22,i*.22+.18))
    pm.instruments.append(track);pm.write(str(path))

def corrupt_first_note(path):
    buf=bytearray(path.read_bytes())
    # explicit note-on status, pitch then velocity; corrupt channel-data pitch
    index=buf.index(bytes([0x90,64,92]))
    buf[index+1]=0xc0
    path.write_bytes(buf)

def test_repair_corrupt_pitch_and_preserve_original():
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'damaged.mid';synth(f,64);corrupt_first_note(f)
        original=f.read_bytes()
        pm=load(f)
        assert f.read_bytes()==original
        assert len(pm.tr1pp_repairs)==1
        assert pm.tr1pp_repairs[0]['before']==192
        assert sum(len(i.notes) for i in pm.instruments)==32
        a=Path(tmp)/'healthy.mid';synth(a,72)
        out,report=arrange([str(f),str(a)],Settings(humanize_ms=0,strict_two_hands=False))
        assert report['sources'][0]['midi_repairs']
        p=Path(tmp)/'arranged.mid';out.write(str(p));assert load(p)

def test_reject_bad_header():
    with pytest.raises(MIDIRepairError):repair_bytes(b'not a midi')

def test_url_validation():
    assert validate_url('https://youtu.be/abc')=='https://youtu.be/abc'
    for url in ['file:///etc/passwd','http://youtu.be/hi','https://example.com/a','https://youtube.com.evil.com']:
        with pytest.raises(ValueError):validate_url(url)
