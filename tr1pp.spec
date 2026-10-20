# PyInstaller spec for native builds. A Linux build is not a Windows executable.
from PyInstaller.utils.hooks import collect_data_files,collect_dynamic_libs,copy_metadata
from importlib.util import find_spec
if find_spec('basic_pitch') is None:
    raise RuntimeError('Run python tools/install_transcription.py before building the full studio')
datas=collect_data_files('basic_pitch')+copy_metadata('basic-pitch')
binaries=collect_dynamic_libs('onnxruntime')
a=Analysis(['main.py'],pathex=[],binaries=binaries,datas=datas,
           hiddenimports=['tr1pp.studio','tr1pp.cli','basic_pitch.inference','basic_pitch.note_creation',
                          'onnxruntime','soundfile','scipy.signal','music21.converter','yt_dlp'],
           hookspath=[],runtime_hooks=[],
           excludes=['tensorflow','torch','coremltools','tflite_runtime','IPython','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='TR1PP Mashup Studio',debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='TR1PP Mashup Studio')
