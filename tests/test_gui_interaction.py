import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/tr1pp-test-cache')
import time
from pathlib import Path
import pytest
import pretty_midi
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tr1pp.editing import MidiEditor
from tr1pp.widgets import PianoRoll
from tr1pp.studio import StudioWindow
from tr1pp.engine import load,arrange,Settings
from tr1pp.project import save_project,load_project

@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def pm():
    midi=pretty_midi.PrettyMIDI();ins=pretty_midi.Instrument(0,name='Piano')
    ins.notes=[pretty_midi.Note(80,72,.5,1.)];midi.instruments=[ins];return midi


def test_mouse_edit_and_clipboard_shortcuts_share_undo_state(app):
    editor=MidiEditor(pm());roll=PianoRoll();roll.bind(editor);roll.show();app.processEvents()
    rect=roll.note_rect(editor.pm.instruments[0].notes[0]);start=rect.center().toPoint()
    QTest.mousePress(roll,Qt.LeftButton,Qt.NoModifier,start)
    QTest.mouseRelease(roll,Qt.LeftButton,Qt.NoModifier,start+QPoint(43,-13))
    assert editor.pm.instruments[0].notes[0].start==pytest.approx(1.)
    assert editor.pm.instruments[0].notes[0].pitch==73
    QTest.keyClick(roll,Qt.Key_C,Qt.ControlModifier);roll.cursor=2
    QTest.keyClick(roll,Qt.Key_V,Qt.ControlModifier)
    assert len(editor.pm.instruments[0].notes)==2 and editor.pm.instruments[0].notes[1].start==2
    QTest.keyClick(roll,Qt.Key_Z,Qt.ControlModifier)
    assert len(editor.pm.instruments[0].notes)==1
    roll.set_midi(editor.pm)
    location=QPoint(int(roll.gutter+3*roll.pixels_per_second),int(roll.ruler+(127-76)*roll.row_height+4))
    QTest.mouseDClick(roll,Qt.LeftButton,Qt.NoModifier,location)
    assert any(n.pitch==76 and n.start==3 for n in editor.pm.instruments[0].notes)
    roll.close()


def wait_for_job(app,window,timeout=15):
    deadline=time.monotonic()+timeout
    while window.worker is not None and time.monotonic()<deadline:
        app.processEvents();QTest.qWait(10)
    app.processEvents()
    assert window.worker is None,'Background job did not complete'


def test_integrated_arrange_edit_mixer_save_reopen_and_background_job(app,tmp_path,monkeypatch):
    monkeypatch.setenv('TR1PP_DATA_DIR',str(tmp_path/'data'))
    window=StudioWindow();window.show();app.processEvents()
    a=Path(__file__).parent/'fixtures'/'Demo Source 1.mid';b=a.with_name('Demo Source 2.mid')
    window.add_item(str(a));window.add_item(str(b))
    window.generated(arrange([a,b],Settings(bridge_bars=2,humanize_ms=0,strict_two_hands=False)))
    assert window.track_select.count()==2 and window.timeline.pm is window.pm
    window.track_select.setCurrentIndex(1);window.roll.selection={0};window.velocity.setValue(42);window.set_selection_velocity()
    assert window.pm is window.editor.pm and window.pm.instruments[1].notes[0].velocity==42
    window.set_mix(1,'pan',.75);window.set_mix(0,'mute',True)
    project=window.capture_project();path=save_project(project,tmp_path/'studio.tr1pp')
    expected=sum(len(i.notes) for i in window.pm.instruments)
    # Async open restores the same edited MIDI, mixer and source files.
    window.load_project_path(path);wait_for_job(app,window)
    assert sum(len(i.notes) for i in window.pm.instruments)==expected
    assert window.pm.instruments[1].notes[0].velocity==42
    assert window.project.mixer[0].mute and window.project.mixer[1].pan==.75
    assert window.paths_now() and all(Path(p).is_file() for p in window.paths_now())
    window.seek(1.25);assert window.roll.cursor==1.25 and window.timeline.cursor==1.25
    window.project.mixer[0].mute=False
    window.play_preview();wait_for_job(app,window)
    assert window.render_path.is_file()
    assert window.player.source().toLocalFile()==str(window.render_path)
    window.stop_preview();window.dirty=False;window.close();app.processEvents()


def test_automation_curve_add_move_delete(app):
    from tr1pp.widgets import AutomationCurve
    curve=AutomationCurve(duration=10);curve.show();app.processEvents()
    point=curve.point_position([2,1]).toPoint()
    QTest.mouseClick(curve,Qt.LeftButton,Qt.NoModifier,point)
    assert len(curve.points)==1 and curve.points[0][0]==pytest.approx(2,abs=.02)
    QTest.mousePress(curve,Qt.LeftButton,Qt.NoModifier,point)
    target=curve.point_position([4,.5]).toPoint()
    QTest.mouseMove(curve,target);QTest.mouseRelease(curve,Qt.LeftButton,Qt.NoModifier,target)
    assert curve.points[0][0]==pytest.approx(4,abs=.03)
    QTest.mouseClick(curve,Qt.RightButton,Qt.NoModifier,target)
    assert not curve.points
    curve.close()


def test_gui_automatic_pipeline_and_bridge_compare_apply(app,tmp_path,monkeypatch):
    monkeypatch.setenv('TR1PP_DATA_DIR',str(tmp_path/'data'))
    window=StudioWindow();window.show();app.processEvents()
    a=Path(__file__).parent/'fixtures'/'Demo Source 1.mid';b=a.with_name('Demo Source 2.mid')
    window.add_item(str(a));window.add_item(str(b));window.bridge.setValue(2)
    window.automatic_workflow();wait_for_job(app,window)
    assert window.report['import_workflow']['sources']
    assert window.workflow_dialog is None and window.transition_select.count()==1
    window.compare_transitions();wait_for_job(app,window)
    assert len(window.transition_candidates)==3
    original=[(n.pitch,n.start,n.end) for i in window.pm.instruments for n in i.notes]
    window.candidate_select.setCurrentIndex(0);window.apply_candidate()
    assert window.report['transitions'][0]['manual_candidate']['candidate']==0
    window.edit_undo()
    assert [(n.pitch,n.start,n.end) for i in window.pm.instruments for n in i.notes]==original
    project=window.capture_project();path=save_project(project,tmp_path/'names.tr1pp')
    window.load_project_path(path);wait_for_job(app,window)
    assert window.items.item(0).text()=='Demo Source 1.mid'
    assert window.capture_project().sources==project.sources
    window.dirty=False;window.close();app.processEvents()
