from pathlib import Path
import ctypes.util
import numpy as np
import pytest
import soundfile as sf
from music21 import converter
from tr1pp.engine import load,export_musicxml
from tr1pp.audio import render_mix

FIX=Path(__file__).parent/'fixtures'/'Demo Source 1.mid'

def test_notation_export_reimports_notes_and_parts(tmp_path):
    midi=load(FIX);path=export_musicxml(midi,tmp_path/'score.musicxml')
    score=converter.parse(str(path))
    actual=sum(len(n.pitches) if n.isChord else 1 for n in score.recurse().notes)
    expected=sum(len(i.notes) for i in midi.instruments)
    # Quantised notation can split tied durations into multiple note elements.
    assert actual>=expected and len(score.parts)==len(midi.instruments)
    pitches={int(p.midi) for n in score.recurse().notes for p in n.pitches}
    assert pitches=={n.pitch for i in midi.instruments for n in i.notes}


def test_real_soundfont_render_when_native_assets_present(tmp_path):
    soundfont=Path('/usr/share/sounds/sf2/TimGM6mb.sf2')
    if not ctypes.util.find_library('fluidsynth') or not soundfont.is_file():
        pytest.skip('Native FluidSynth plus test SoundFont unavailable on this platform')
    path=render_mix(load(FIX),tmp_path/'sampled.flac',soundfont=soundfont)
    audio,rate=sf.read(path)
    assert audio.shape[1]==2 and rate==22050 and np.max(np.abs(audio))>.01
