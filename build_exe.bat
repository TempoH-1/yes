@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat and install_transcription.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m pip install "pyinstaller>=6.10,<7"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean tr1pp.spec
if errorlevel 1 exit /b 1
echo Build produced in dist\TR1PP Mashup Studio. Test on a clean Windows machine before release.
echo FFmpeg, a FluidSynth DLL, and a licensed piano SF2 require separate installation/distribution.
exit /b 0
