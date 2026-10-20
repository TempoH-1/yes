"""Reproducible CPU benchmark, recording observations without universal promises."""
from pathlib import Path
import json,sys,time,tempfile,platform,copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tr1pp.engine import load,arrange,Settings
from tr1pp.editing import MidiEditor
from tr1pp.audio import render_mix
from tr1pp.project import Project,save_project,load_project
root=Path(__file__).resolve().parents[1]
files=[root/'tests/fixtures/complex_generated_a.mid',root/'tests/fixtures/complex_generated_b.mid']
results={}
def measure(name,fn):
    start=time.perf_counter();result=fn();results[name]=round(time.perf_counter()-start,4);return result
with tempfile.TemporaryDirectory() as tmp:
    midi,report=measure('arrange_seconds',lambda:arrange(files,Settings(bridge_bars=2,humanize_ms=0,strict_two_hands=False)))
    editor=measure('editor_load_seconds',lambda:MidiEditor(midi))
    measure('move_group_seconds',lambda:editor.move_notes(1,range(min(500,len(editor.pm.instruments[1].notes))),.25,1))
    project=Project(midi=editor.pm,sources=list(map(str,files)),report=report)
    path=measure('save_project_seconds',lambda:save_project(project,Path(tmp)/'p.tr1pp'))
    restored=measure('load_project_seconds',lambda:load_project(path))
    measure('synthetic_render_8khz_seconds',lambda:render_mix(restored.midi,Path(tmp)/'preview.wav',rate=8000))
    results.update(note_count=sum(len(i.notes) for i in midi.instruments),duration_seconds=round(midi.get_end_time(),3),
                   project_bytes=path.stat().st_size,platform=platform.platform(),python=platform.python_version())
print(json.dumps(results,indent=2))
