"""Headless application service for the complete import-to-editable-project path."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Callable
import copy
import threading
from .engine import Settings,load,analyse,arrange
from .imports import AUDIO,MIDI,acquire
from .transcription import TranscriptionOptions,transcribe
from .planning import preset_plan,render_plan
from .project import Project

class WorkflowCancelled(RuntimeError): pass


def prepare_project(sources, directory, settings=None, structure='Complete sources + bridges',
                    options=None, progress: Callable[[int,str],None] | None=None,
                    cancel: threading.Event | None=None):
    """Import, transcribe, analyse and arrange in one reusable operation.

    Partial source failures are reported, never silently substituted. At least
    one usable MIDI is required; two or more produce an arrangement. Original
    recordings remain available as embedded inactive provenance assets.
    """
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    settings=settings or Settings();options=options or TranscriptionOptions()
    if not sources:raise ValueError('Select at least one music source')
    if len(sources)>32:raise ValueError('Import at most 32 sources per workflow')
    active=[];reports=[];errors=[];assets={}
    def emit(value,message):
        if progress:progress(value,message)
    def check_cancel():
        if cancel is not None and cancel.is_set():raise WorkflowCancelled('Workflow cancelled; cached completed imports remain available')
    for index,source in enumerate(sources):
        check_cancel();source=str(source);emit(round(index/len(sources)*75),'Importing '+Path(source).name)
        try:
            path=acquire(source,directory/'downloads') if source.startswith('https://') else source
            if not Path(path).is_file():raise FileNotFoundError(path)
            extension=Path(path).suffix.lower();record={'source':source,'local_path':path}
            if extension in MIDI:
                midi=load(path);result_path=path
            elif extension in AUDIO:
                def model_progress(value,message):
                    emit(round((index+value/100)/len(sources)*75),message)
                result=transcribe(path,directory/'transcriptions',options,model_progress)
                check_cancel();result_path=result['midi_path'];midi=load(result_path)
                record['transcription']=result
                # Project size checks are enforced by save_project; do not invent links
                # to source material that will disappear when a task workspace changes.
                if sum(map(len,assets.values()))+Path(path).stat().st_size>512*1024*1024:raise ValueError('Source exceeds portable project size limit')
                assets[path]=Path(path).read_bytes()
            else:raise ValueError('Unsupported source format: '+extension)
            record['analysis']=analyse(midi);record['midi_path']=result_path
            active.append(str(result_path));reports.append(record)
        except WorkflowCancelled:raise
        except Exception as e:errors.append({'source':source,'error':str(e)})
    check_cancel()
    if not active:raise ValueError('No usable sources: '+'; '.join(e['error'] for e in errors))
    emit(80,'Building editable arrangement')
    if len(active)==1:
        midi=load(active[0]);report={'sources':[reports[0]['analysis']],'source_regions':[], 'transitions':[],
                                      'implementation':'One source opened for editing; no combined arrangement generated.'}
    elif structure=='Complete sources + bridges':midi,report=arrange(active,settings)
    else:
        plan=preset_plan(active,structure,settings.target_bpm or 120,settings.difficulty)
        midi,report=render_plan(active,plan)
    check_cancel();report['import_workflow']={'sources':reports,'errors':errors}
    project=Project(midi=midi,sources=active,settings={**asdict(settings),'structure':structure},
                    report=report,assets=assets,
                    markers=[{'time':r['start'],'label':r.get('label',f"Source {r['source_index']+1}")} for r in report.get('source_regions',[])])
    project.source_names={r['midi_path']:Path(r['local_path']).stem+(' (transcribed).mid' if r.get('transcription') else Path(r['local_path']).suffix) for r in reports}
    project.sync_tracks();emit(100,'Editable project ready');return project
