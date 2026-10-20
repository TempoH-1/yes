# Continuing development checkpoint — TR1PP Mashup Studio 2.0

This is a coherent, persistent development tree in `/workspace/yes`, based on the
uploaded `TR1PP_Mashup_Studio_v1.1_verified_progress.zip`. It is not a final release
or a claim that the requested two-hour development target was met. No remote
push or Windows build has occurred. The GitHub repository was empty; the current
source is local work in the checkout, not a remotely recoverable main commit.
Keep this workspace or publish its environment snapshot before discarding it.

## Current phase

The first integration phase connects import/transcription, symbolic analysis,
source-derived arrangement planning, actual note editing, timeline, stereo
mixing/rendering, exports and portable project/recovery storage. Preserve this
same codebase in subsequent turns; do not restart from the old ZIP or create a
new minor release just to mark a checkpoint.

The original MIDI algorithms remain in `engine.py`, `composition.py`,
`music_theory.py`, `quality_metrics.py` and `midi_repair.py`. `gui.py` retains the
original source collection/control shell. `studio.py` integrates the new views
and services. Core services are `workflow.py`, `transcription.py`, `planning.py`,
`editing.py`, `project.py`, `audio.py`; `widgets.py` implements editing/timeline/
automation views. `cli.py` exercises the same workflow without a desktop.

## Resume commands

```bash
cd /workspace/yes
export TR1PP_DATA_DIR=/workspace/tr1pp-state
export XDG_CACHE_HOME=/workspace/tr1pp-cache
QT_QPA_PLATFORM=offscreen TR1PP_TEST_MODEL=1 /workspace/tr1pp-venv/bin/python -m pytest -q
/workspace/tr1pp-venv/bin/python -m tr1pp doctor
/workspace/tr1pp-venv/bin/python tools/benchmark.py
```

If dependencies need recreation, use `bash tools/setup_cloud.sh`. Tasks are
already isolated; use this checkout and do not create a Git worktree unless the
user explicitly requests one. `requirements-cloud.lock` records the tested Linux
versions. The Basic Pitch model is installed in the virtual environment and is
loaded through ONNX, not downloaded during prediction. Project caches, settings,
recovery and history default to platform application data; the cloud override
above keeps them writable and persistent under `/workspace`.

## Next implementation actions, in order

1. Run the current full suite before changing behavior. Preserve all original
   regression fixtures and the new actual model/GUI/project integration tests.
2. Exercise real public URL importing only after egress settings change. Inspect
   yt-dlp responses and redirects/JS requirements; don't treat a proxy 403 as a
   missing user credential. Add per-source progress/cancellation integration for
   downloading, and validate direct URLs against a controlled test media server.
3. Introduce a first-class audio-clip/session model (source asset, offset, trim,
   gain, stretch, fades) alongside MIDI, with transactional editing and portable
   persistence. Implement waveform lanes, cut/move/fade, mixed audio+MIDI render
   and restartable transport before claiming a complete DAW.
4. Separate `StudioWindow` into source/session, transport and mixer controllers
   as audio-clip work expands. Retain one authoritative session state, avoid
   parallel stale MIDI owners, and extend unified history to mixer/markers.
5. Build a piano transcription evaluation corpus with licensed recordings and
   note references. Measure onset/pitch/offset metrics, pedal and dense piano
   errors; compare a dedicated pretrained piano model through a typed backend
   interface. Verify model licensing, trusted artifacts and runtime requirements
   before adding another heavyweight dependency. Keep quality claims bounded.
6. Make arrangement editing clip-aware: preserve source identities through
   regeneration, add phrase-level candidate comparison, local chord-aware
   voice leading and tempo ramps. Test boundary timing/controllers and include
   human listening evaluation. Do not rename heuristics as generative AI.
7. Execute `.github/workflows/windows.yml` on a Windows runner. Diagnose native
   FluidSynth/FFmpeg discovery and bundling, test real audio devices, then test
   a built app on a clean Windows VM. Add an installer and signing only after
   those pass. Current build files do not establish executable compatibility.
8. Extend the piano roll with a velocity lane, expression/controller editing,
   track-aware selection history and score linkage. Benchmark redraws/undo on
   larger real MIDI files before expanding performance claims.

## Known issues and verification

See KNOWN_ISSUES.md and VERIFICATION_REPORT.md. Do not collapse environment
restrictions, known product gaps and test failures into a single "complete" label.
The old v1.1 documentation is retained under `docs/history/`; it is historical.
