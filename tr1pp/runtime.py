"""Capability diagnostics; never read credentials or enumerate environment values."""
from __future__ import annotations
import ctypes.util
import importlib.metadata
import platform
from pathlib import Path
import shutil

def diagnose():
    from .transcription import model_status
    packages={}
    for name in ['PySide6','pretty_midi','numpy','librosa','soundfile','pyfluidsynth','yt-dlp','onnxruntime','basic-pitch','music21']:
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    soundfonts=[str(p) for root in ['/usr/share/sounds/sf2','/usr/share/soundfonts'] if Path(root).is_dir() for p in Path(root).glob('*.sf2')]
    return {'python':platform.python_version(),'platform':platform.system(),'packages':packages,
            'ffmpeg':shutil.which('ffmpeg'),'fluidsynth_library':ctypes.util.find_library('fluidsynth'),
            'system_soundfonts':soundfonts,'transcription':model_status(),
            'limitations':['Audio device playback requires a desktop/audio backend',
                           'Basic Pitch ONNX-only install deliberately omits its unused TensorFlow metadata dependency',
                           'Windows EXE needs native Windows build and testing']}
