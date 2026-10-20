@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m pip install --no-deps -e .
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m tr1pp doctor
if errorlevel 1 goto :failed
echo Core setup complete. Run install_transcription.bat for pretrained ONNX transcription.
echo FFmpeg and the FluidSynth native library are external dependencies. See README.md.
exit /b 0
:failed
echo Setup failed. Read the error above. Python 3.12 is required.
exit /b 1
