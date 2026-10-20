"""Opt-in real model test: TR1PP_TEST_MODEL=1, no mocks or network downloads."""
import os
from pathlib import Path
import numpy as np
import pretty_midi
import pytest
import soundfile as sf
from tr1pp.transcription import TranscriptionOptions,decode_audio,transcribe,model_status
from tr1pp.audio import render_mix
from tr1pp.engine import analyse,load
from tr1pp.project import Project,save_project,load_project
from tr1pp.editing import MidiEditor


def test_decode_rejects_silence_length_and_invalid_settings(tmp_path):
    source=tmp_path/'silent.wav';sf.write(source,np.zeros(44100),22050)
    with pytest.raises(ValueError,match='exceeds'):decode_audio(source,tmp_path/'decoded.wav',max_seconds=.5)
    with pytest.raises(ValueError):TranscriptionOptions(minimum_pitch=100,maximum_pitch=21).validate()
    with pytest.raises(ValueError):TranscriptionOptions(frame_threshold=float('nan')).validate()


@pytest.mark.skipif(os.environ.get('TR1PP_TEST_MODEL')!='1',reason='Opt-in pretrained model integration; set TR1PP_TEST_MODEL=1')
def test_actual_pretrained_model_audio_to_editable_portable_midi(tmp_path):
    assert model_status()['available']
    midi=pretty_midi.PrettyMIDI();ins=pretty_midi.Instrument(0)
    expected=[60,64,67,72]
    ins.notes=[pretty_midi.Note(100,pitch,ix*.7+.1,ix*.7+.6) for ix,pitch in enumerate(expected)]
    midi.instruments=[ins];audio=render_mix(midi,tmp_path/'input.wav')
    options=TranscriptionOptions(minimum_confidence=.15,minimum_note_ms=70)
    progress=[];result=transcribe(audio,tmp_path/'cache',options,lambda n,m:progress.append(n))
    assert len(result['notes'])>=4 and 0<result['mean_activation']<=1
    # Actual pitch/time recovery: each input note must have a model-detected match.
    for ix,pitch in enumerate(expected):
        assert any(n['pitch']==pitch and abs(n['start']-(ix*.7+.1))<.18 for n in result['notes'])
    assert progress[-1]==100
    cached=transcribe(audio,tmp_path/'cache',options);assert cached['cache_hit']
    transcription=load(result['midi_path']);assert analyse(transcription)['notes']>=4
    editor=MidiEditor(transcription);editor.add(0,76,3,.2)
    project=Project(midi=editor.pm,sources=[str(audio)],report={'transcription':result})
    restored=load_project(save_project(project,tmp_path/'p.tr1pp'))
    assert any(n.pitch==76 for i in restored.midi.instruments for n in i.notes)
    output=render_mix(restored.midi,tmp_path/'result.flac');assert sf.info(output).channels==2
    silent=tmp_path/'silence.wav';sf.write(silent,np.zeros(22050),22050)
    with pytest.raises(ValueError,match='silent'):transcribe(silent,tmp_path/'cache')
