from pathlib import Path
import json
import zipfile
import pytest
import pretty_midi
from tr1pp.project import Project,TrackMix,save_project,load_project,materialize_sources,snapshot
from tr1pp.engine import load

FIX=Path(__file__).parent/'fixtures'/'Demo Source 1.mid'

def test_portable_project_sources_mixer_metadata_and_history(tmp_path):
    source=tmp_path/'a.mid';source.write_bytes(FIX.read_bytes())
    audio_origin=str(tmp_path/'original.wav')
    project=Project(midi=load(source),sources=[str(source)],settings={'mode':'Classical'},
                    report={'transcription':{'backend':'test'}},markers=[{'time':1.,'label':'Verse'}],
                    assets={audio_origin:b'provenance-only audio'})
    project.sync_tracks();project.mixer[0]=TrackMix(volume=.4,pan=-.7,solo=True,automation=[[0,0],[2,1]])
    out=save_project(project,tmp_path/'portable.tr1pp');source.unlink()
    restored=load_project(out)
    assert restored.settings==project.settings and restored.report==project.report
    assert restored.midi.instruments[0].notes[0].pitch==project.midi.instruments[0].notes[0].pitch
    assert restored.mixer[0].automation==[[0,0],[2,1]]
    assert restored.assets[audio_origin]==b'provenance-only audio'
    assert audio_origin not in restored.sources
    paths=materialize_sources(restored,tmp_path/'restored')
    assert len(paths)==1 and Path(paths[0]).read_bytes()==FIX.read_bytes()
    assert materialize_sources(restored,tmp_path/'restored')==paths
    for _ in range(5):snapshot(restored,tmp_path/'history',keep=3)
    assert len(list((tmp_path/'history').glob('*.tr1pp')))==3


def test_failed_save_preserves_previous_project(tmp_path):
    project=Project(midi=load(FIX));path=save_project(project,tmp_path/'p.tr1pp');old=path.read_bytes()
    project.settings={'nonserializable':object()}
    with pytest.raises(TypeError):save_project(project,path)
    assert path.read_bytes()==old


def test_reject_unsafe_archive_and_checksum(tmp_path):
    path=tmp_path/'unsafe.tr1pp'
    with zipfile.ZipFile(path,'w') as z:z.writestr('../outside','data')
    with pytest.raises(ValueError,match='Unsafe'):load_project(path)
    project=Project(midi=load(FIX),sources=[str(FIX)])
    save_project(project,path)
    with zipfile.ZipFile(path) as z:members={name:z.read(name) for name in z.namelist()}
    source_name=next(name for name in members if name.startswith('sources/'));members[source_name]=b'corrupt'
    with zipfile.ZipFile(path,'w') as z:
        for name,content in members.items():z.writestr(name,content)
    with pytest.raises(ValueError,match='checksum'):load_project(path)


def test_legacy_project_migration(tmp_path):
    (tmp_path/'source.mid').write_bytes(FIX.read_bytes())
    path=tmp_path/'old.json';path.write_text(json.dumps({'format':'tr1pp-project-v1','sources':[],'export_midi':'source.mid'}))
    assert load_project(path).midi.instruments[0].notes

@pytest.mark.parametrize('mix',[TrackMix(volume=float('nan')),TrackMix(pan=2),TrackMix(automation=[[1,0],[1,1]]),TrackMix(automation=[[0,-1]])])
def test_mixer_validation(mix):
    with pytest.raises(ValueError):mix.validate()


def test_empty_tracks_and_exact_note_timing_survive_project_roundtrip(tmp_path):
    midi=pretty_midi.PrettyMIDI();empty=pretty_midi.Instrument(0,name='Empty left hand')
    right=pretty_midi.Instrument(0,name='Right hand');right.notes=[pretty_midi.Note(83,72,.1234567,.8765432)]
    midi.instruments=[empty,right]
    project=Project(midi=midi,mixer=[TrackMix(volume=.1),TrackMix(pan=.9)])
    restored=load_project(save_project(project,tmp_path/'empty.tr1pp'))
    assert len(restored.midi.instruments)==2 and not restored.midi.instruments[0].notes
    assert restored.midi.instruments[1].notes[0].start==.1234567
    assert restored.mixer[1].pan==.9
