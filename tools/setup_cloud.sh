#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tr1pp_venv="${TR1PP_VENV:-/workspace/tr1pp-venv}"
tr1pp_python="${TR1PP_PYTHON:-python}"
"$tr1pp_python" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/workspace/tr1pp-pip-cache}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/workspace/tr1pp-cache}"
export TR1PP_DATA_DIR="${TR1PP_DATA_DIR:-/workspace/tr1pp-state}"
mkdir -p "$PIP_CACHE_DIR" "$XDG_CACHE_HOME" "$TR1PP_DATA_DIR"
if [ ! -x "$tr1pp_venv/bin/python" ]; then "$tr1pp_python" -m venv "$tr1pp_venv"; fi
"$tr1pp_venv/bin/python" -m pip install -r requirements-cloud.lock
"$tr1pp_venv/bin/python" tools/install_transcription.py
"$tr1pp_venv/bin/python" -m pip install --no-deps --no-build-isolation -e .
command -v ffmpeg >/dev/null || { echo 'FFmpeg is required for the tested audio import/export workflow.' >&2; exit 1; }
"$tr1pp_venv/bin/python" -m tr1pp doctor
QT_QPA_PLATFORM=offscreen TR1PP_TEST_MODEL=1 "$tr1pp_venv/bin/python" -m pytest -q
