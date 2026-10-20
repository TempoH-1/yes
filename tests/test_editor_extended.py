import copy
from io import BytesIO
import pretty_midi
import pytest
from tr1pp.editing import MidiEditor

def midi():
    pm=pretty_midi.PrettyMIDI(initial_tempo=120)
    ins=pretty_midi.Instrument(0,name='Piano')
    ins.notes=[pretty_midi.Note(80,48,.1,.5),pretty_midi.Note(90,72,.4,.7)]
    ins.control_changes=[pretty_midi.ControlChange(64,100,.2)]
    ins.pitch_bends=[pretty_midi.PitchBend(123,.3)]
    pm.instruments=[ins];return pm

def test_group_movement_clamps_rigidly_and_undoes():
    e=MidiEditor(midi());e.move_notes(0,[0,1],-1,120)
    a,b=e.pm.instruments[0].notes
    assert a.start==0 and b.start==pytest.approx(.3)
    assert b.pitch==127 and a.pitch==103
    assert e.undo() and e.pm.instruments[0].notes[0].pitch==48
    assert e.redo() and e.pm.instruments[0].notes[0].start==0

def test_full_tempo_change_and_track_shift_preserve_beats_events():
    e=MidiEditor(midi());e.set_tempo(60)
    ins=e.pm.instruments[0]
    assert ins.notes[0].start==pytest.approx(.2)
    assert ins.control_changes[0].time==pytest.approx(.4)
    assert ins.pitch_bends[0].time==pytest.approx(.6)
    assert e.pm.get_tempo_changes()[1][0]==pytest.approx(60)
    data=BytesIO();e.pm.write(data);reloaded=pretty_midi.PrettyMIDI(BytesIO(data.getvalue()))
    assert reloaded.instruments[0].notes[0].start==pytest.approx(.2,abs=.005)
    e.shift_track(0,1);assert e.pm.instruments[0].control_changes[0].time==pytest.approx(1.4)
    assert e.undo() and e.undo()
    assert e.pm.get_tempo_changes()[1][0]==pytest.approx(120)


def test_selection_transaction_clipboard_and_split():
    e=MidiEditor(midi());e.set_velocities(0,[0,1],60);assert len(e.undo_stack)==1
    e.delete_many(0,[0,1]);assert not e.pm.instruments[0].notes
    e.undo();assert len(e.pm.instruments[0].notes)==2
    copied=e.copy_passage(0,[0,1]);e.paste_passage(0,copied,2)
    assert e.pm.instruments[0].notes[2].start==2
    e.assign_hands();assert len(e.pm.instruments)==2
    assert all(n.pitch<60 for n in e.pm.instruments[0].notes)
    assert all(n.pitch>=60 for n in e.pm.instruments[1].notes)
    assert e.pm.instruments[0].control_changes and e.pm.instruments[1].control_changes
    assert e.undo() and len(e.pm.instruments)==1


def test_humanize_is_reproducible_and_failed_transaction_is_clean():
    a=MidiEditor(midi());b=MidiEditor(midi())
    a.humanize(0,[0,1],12,seed=5);b.humanize(0,[0,1],12,seed=5)
    assert a.pm.instruments[0].notes[0].start==b.pm.instruments[0].notes[0].start
    count=len(a.undo_stack)
    with pytest.raises(IndexError):a.delete_many(0,[0,100])
    assert len(a.undo_stack)==count

@pytest.mark.parametrize('operation',[
 lambda e:e.add(0,60,float('nan'),1),
 lambda e:e.change(0,0,end=float('inf')),
 lambda e:e.transform(0,[0],quantize=-1),
 lambda e:e.transform(0,[0,-1],transpose=1),
 lambda e:e.pedal(0,-2,-1),
 lambda e:e.move_notes(0,[0],time_delta=float('nan')),
 lambda e:e.paste_passage(0,e.copy_passage(0,[0]),-1),
])
def test_invalid_edits_are_atomic(operation):
    e=MidiEditor(midi())
    with pytest.raises((ValueError,IndexError)):operation(e)
    assert not e.undo_stack
    assert e.pm.instruments[0].notes[0].start==.1
