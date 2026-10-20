from pathlib import Path
import copy
import pretty_midi
import pytest
from tr1pp.planning import Clip,ArrangementPlan,preset_plan,render_plan,harmonic_timeline
from tr1pp.engine import load
from tr1pp.editing import MidiEditor

FIX=Path(__file__).parent/'fixtures'
FILES=[FIX/'Demo Source 1.mid',FIX/'Demo Source 2.mid']

@pytest.mark.parametrize('preset',['A/B/A thematic','Layered motifs','Call and response'])
def test_distinct_structures_and_exportable_plans(tmp_path,preset):
    plan=preset_plan(FILES,preset,bpm=100,difficulty=100)
    midi,report=render_plan(FILES,plan)
    assert midi.instruments and report['quality']['note_count']>20
    assert report['quality']['invalid_note_lengths']==0
    assert midi.get_tempo_changes()[1][0]==pytest.approx(100)
    if preset=='Layered motifs':assert all(region['start']==0 for region in report['source_regions'])
    else:assert report['source_regions'][1]['start']>0
    if preset=='A/B/A thematic':assert report['source_regions'][-1]['source_index']==0
    out=tmp_path/'plan.mid';midi.write(str(out));assert load(out).instruments
    restored=ArrangementPlan.from_dict(report['plan']);assert restored==plan


def test_explicit_clip_times_gain_transpose_repeats_and_controllers(tmp_path):
    midi=pretty_midi.PrettyMIDI(initial_tempo=120);ins=pretty_midi.Instrument(0,name='Piano')
    ins.notes=[pretty_midi.Note(100,60,0,.5),pretty_midi.Note(80,64,.5,1)]
    ins.control_changes=[pretty_midi.ControlChange(64,100,.1),pretty_midi.ControlChange(64,0,.9)]
    midi.instruments=[ins];path=tmp_path/'source.mid';midi.write(str(path))
    plan=ArrangementPlan(bpm=60,clips=[Clip(0,.25,1,4,transpose=2,gain=.5,repeats=2)])
    out,report=render_plan([path],plan);notes=out.instruments[0].notes
    assert len(notes)==4 and notes[0].start==4 and notes[0].end==4.5
    assert notes[0].pitch==62 and notes[0].velocity==50
    assert notes[2].start==5.5
    assert any(c.number==64 and c.value==100 and c.time==4 for c in out.instruments[0].control_changes)
    assert report['source_regions'][0]['end']==7


def test_difficulty_reduction_is_effective_and_reported():
    dense=[FIX/'complex_generated_a.mid',FIX/'complex_generated_b.mid']
    full=preset_plan(dense,'Layered motifs',difficulty=100)
    simple=copy.deepcopy(full);simple.difficulty=0
    a,ra=render_plan(dense,full);b,rb=render_plan(dense,simple)
    assert rb['quality']['note_count']<ra['quality']['note_count']
    assert rb['quality']['notes_reduced_by_difficulty']>0


def test_chord_estimates_from_triad_not_arbitrary_labels():
    midi=pretty_midi.PrettyMIDI(initial_tempo=120);ins=pretty_midi.Instrument(0)
    ins.notes=[pretty_midi.Note(90,p,0,2) for p in (48,60,64,67)]+[pretty_midi.Note(90,p,2,4) for p in (45,57,60,64)]
    midi.instruments=[ins];chords=harmonic_timeline(midi)
    assert chords[0]['chord']=='C major' and chords[0]['coverage']==1
    assert chords[1]['chord']=='A minor' and chords[1]['coverage']==1


def test_transition_region_replacement_preserves_outside_and_undo():
    midi=pretty_midi.PrettyMIDI();ins=pretty_midi.Instrument(0,name='Right Hand')
    ins.notes=[pretty_midi.Note(80,72,0,5),pretty_midi.Note(80,74,2.2,2.5)]
    midi.instruments=[ins];editor=MidiEditor(midi)
    new=pretty_midi.PrettyMIDI();track=pretty_midi.Instrument(0);track.notes=[pretty_midi.Note(90,76,.2,.8)];new.instruments=[track]
    editor.replace_region(2,3,new)
    actual={(n.pitch,n.start,n.end) for n in editor.pm.instruments[0].notes}
    assert (72,0,2) in actual and (72,3,5) in actual and (76,2.2,2.8) in actual
    assert not any(n.pitch==74 for n in editor.pm.instruments[0].notes)
    assert editor.undo() and len(editor.pm.instruments[0].notes)==2


def test_invalid_plan_fails_before_rendering():
    with pytest.raises(ValueError,match='source index'):render_plan(FILES,ArrangementPlan(clips=[Clip(5,0,1,0)]))
    with pytest.raises(ValueError,match='after its source'):render_plan(FILES,ArrangementPlan(clips=[Clip(0,0,999,0)]))
