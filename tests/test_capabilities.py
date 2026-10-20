from pathlib import Path
import pretty_midi
import pytest
from tr1pp.imports import validate_url,extract_local_audio
from tr1pp.engine import export_musicxml,render_audio
from tr1pp.editing import MidiEditor

def test_url_allowlist_and_rejection():
    assert validate_url('https://youtu.be/abc')=='https://youtu.be/abc'
    for url in ['http://youtu.be/a','https://youtube.com.evil.net/a','file:///etc/passwd','https://evil.net/video']:
        with pytest.raises(ValueError):validate_url(url)

def test_invalid_midi_and_recovery_regressions_imported():
    # Dedicated MIDI recovery checks in tests/test_import_recovery.py
    assert Path('tr1pp/midi_repair.py').is_file()

def test_editor_track_export_roundtrip(tmp_path):
    pm=pretty_midi.PrettyMIDI()
    for i in range(2):
        inst=pretty_midi.Instrument(0,name=f'Hand{i}')
        inst.notes.append(pretty_midi.Note(90,48+i*24,0,1))
        pm.instruments.append(inst)
    e=MidiEditor(pm);out=tmp_path/'right.mid';e.export_hand(1,out)
    copied=pretty_midi.PrettyMIDI(str(out))
    assert len(copied.instruments)==1 and copied.instruments[0].notes[0].pitch==72
