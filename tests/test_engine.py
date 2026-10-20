import tempfile
import json
from pathlib import Path
import pretty_midi
from tr1pp.engine import Settings,arrange,analyse

def fake(pitch,path):
    pm=pretty_midi.PrettyMIDI(initial_tempo=120)
    inst=pretty_midi.Instrument(0)
    for i in range(48):
        n=pretty_midi.Note(80,pitch+(i%5),i*.19,i*.19+.16);inst.notes.append(n)
    pm.instruments.append(inst);pm.write(str(path))

def test_two_source_arrangement():
    with tempfile.TemporaryDirectory() as tmp:
        a=Path(tmp)/'a.mid';b=Path(tmp)/'b.mid';fake(64,a);fake(72,b)
        pm,report=arrange([str(a),str(b)],Settings(humanize_ms=0,strict_two_hands=False))
        json.dumps(report)  # Regression: scoring metadata must not contain cycles
        assert len(pm.instruments)==2
        assert len(report['transitions'])==1
        assert report['quality']['note_count']>=96
        assert report['quality']['invalid_note_lengths']==0
        assert any(n.pitch==64 for i in pm.instruments for n in i.notes)
        assert any(n.pitch==72 for i in pm.instruments for n in i.notes)
        f=Path(tmp)/'result.mid';pm.write(str(f));assert f.stat().st_size>100
