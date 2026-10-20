"""Executed full MIDI pipeline with two high-density GENERATED (not original song) fixtures."""
from pathlib import Path
import json
import pretty_midi
from tr1pp.engine import analyse,arrange,Settings,load
from tr1pp.editing import MidiEditor
from tr1pp.preview import render_preview

FIXTURES=Path(__file__).parent/'fixtures'

def test_full_pipeline(tmp_path):
    a,b=(FIXTURES/'complex_generated_a.mid',FIXTURES/'complex_generated_b.mid')
    input_a=load(a);input_b=load(b)
    info_a,info_b=analyse(input_a),analyse(input_b)
    assert info_a['notes']>1000 and info_b['notes']>1000
    output,report=arrange([a,b],Settings(bridge_bars=3,humanize_ms=0,strict_two_hands=False))
    assert report['transitions'] and len(report['transitions'][0]['candidate_evaluation']['compared'])==3
    baseline=sum(len(ins.notes) for ins in output.instruments)
    editor=MidiEditor(output)
    ix=editor.add(1,80,1,.2,90)
    assert len(editor.pm.instruments[1].notes)==len(output.instruments[1].notes)+1
    editor.change(1,ix,pitch=81)
    assert editor.pm.instruments[1].notes[ix].pitch==81
    assert editor.undo() and editor.pm.instruments[1].notes[ix].pitch==80
    assert editor.redo() and editor.pm.instruments[1].notes[ix].pitch==81
    wav=render_preview(editor.pm,tmp_path/'preview.wav',sample_rate=8000)
    assert wav.stat().st_size>1000
    mid=tmp_path/'export.mid';editor.pm.write(str(mid))
    reimport=load(mid)
    assert len([n for ins in reimport.instruments for n in ins.notes])==baseline+1
    assert any(n.pitch==81 and abs(n.start-1)<.01 for ins in reimport.instruments for n in ins.notes)
    # Both source motifs are present in the output, independent of the bridge's added notes.
    out_pitches={n.pitch for ins in reimport.instruments for n in ins.notes}
    assert len(out_pitches & {n.pitch for n in input_a.instruments[0].notes})>=4
    assert len(out_pitches & {n.pitch for n in input_b.instruments[0].notes})>=4
    assert report['quality']['invalid_note_lengths']==0
    (tmp_path/'report.json').write_text(json.dumps(report))

def test_failed_edit_does_not_pollute_undo():
    pm=pretty_midi.PrettyMIDI();pm.instruments.append(pretty_midi.Instrument(0))
    editor=MidiEditor(pm)
    try:editor.add(0,64,0,-1)
    except ValueError:pass
    else:assert False,'expected ValueError'
    assert not editor.undo_stack
    try:editor.pedal(0,2,1)
    except ValueError:pass
    else:assert False,'expected ValueError'
    assert not editor.undo_stack
