from pathlib import Path
import threading
import os
import numpy as np
import pretty_midi
import pytest
from tr1pp.workflow import prepare_project,WorkflowCancelled
from tr1pp.engine import Settings
from tr1pp.project import load_project,save_project
from tr1pp.audio import render_mix
from tr1pp.cli import main

FIX=Path(__file__).parent/'fixtures'
SOURCES=[str(FIX/'Demo Source 1.mid'),str(FIX/'Demo Source 2.mid')]

def test_complete_workflow_reports_partial_failures_and_embeds_sources(tmp_path):
    progress=[]
    project=prepare_project(SOURCES+['missing.mid'],tmp_path/'cache',Settings(humanize_ms=0),
                            structure='Call and response',progress=lambda n,m:progress.append(n))
    assert project.midi.instruments and len(project.sources)==2
    assert project.report['import_workflow']['errors'][0]['source']=='missing.mid'
    assert progress[-1]==100
    path=save_project(project,tmp_path/'workflow.tr1pp')
    restored=load_project(path);assert len(restored.sources)==2 and len(restored.assets)==2


def test_cancellation_does_not_return_partial_project(tmp_path):
    cancel=threading.Event();cancel.set()
    with pytest.raises(WorkflowCancelled):prepare_project(SOURCES,tmp_path,cancel=cancel)
    with pytest.raises(ValueError,match='No usable sources'):prepare_project(['nonexistent.wav'],tmp_path)


def test_headless_cli_build_render_and_errors(tmp_path,capsys):
    project=tmp_path/'test.tr1pp';midi=tmp_path/'test.mid';audio=tmp_path/'test.flac'
    assert main(['build',*SOURCES,'--project',str(project),'--midi',str(midi),'--cache-dir',str(tmp_path/'cache'),'--bridge-bars','2'])==0
    assert project.is_file() and midi.is_file()
    assert main(['render',str(project),str(audio)])==0 and audio.is_file()
    assert main(['render','missing.tr1pp',str(audio)])==1
    assert main(['build',SOURCES[0],'missing.mid','--project',str(project),'--cache-dir',str(tmp_path/'cache')])==2

@pytest.mark.skipif(os.environ.get('TR1PP_TEST_MODEL')!='1',reason='Opt-in real model pipeline')
def test_automatic_audio_plus_midi_pipeline(tmp_path):
    midi=pretty_midi.PrettyMIDI();ins=pretty_midi.Instrument(0)
    ins.notes=[pretty_midi.Note(100,pitch,.1+ix*.7,.6+ix*.7) for ix,pitch in enumerate([60,64,67,72])]
    midi.instruments=[ins];audio=render_mix(midi,tmp_path/'recording.wav')
    project=prepare_project([str(audio),SOURCES[0]],tmp_path/'cache',Settings(bridge_bars=2,humanize_ms=0))
    assert len(project.sources)==2 and project.report['transitions']
    assert project.report['import_workflow']['sources'][0]['transcription']['notes']
    assert str(audio) in project.assets
    restored=load_project(save_project(project,tmp_path/'complete.tr1pp'))
    assert str(audio) in restored.assets and str(audio) not in restored.sources
