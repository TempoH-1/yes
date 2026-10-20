# TR1PP Mashup Studio 2.0 — continuing development

One development codebase, expanded from the supplied v1.1 archive. This is a
recoverable engineering checkpoint, not a completed commercial DAW or final
release. Existing arrangement and MIDI recovery behavior remains covered by its
original regression tests. Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Current state and next work: [DEVELOPMENT_CHECKPOINT.md](DEVELOPMENT_CHECKPOINT.md).

## Run in this cloud workspace

```bash
cd /workspace/yes
bash tools/setup_cloud.sh
export TR1PP_DATA_DIR=/workspace/tr1pp-state
/workspace/tr1pp-venv/bin/python main.py
```

A desktop display is needed for interactive GUI use. For internal cloud GUI
validation use `QT_QPA_PLATFORM=offscreen`; the cloud machine has no audio output
device. SoundFont rendering to files is supported and tested independently.
The setup script uses Python 3.12, a separate virtual environment, the exact tested
Linux dependency lock, the upstream pretrained model and real regression/model
checks. FFmpeg must be available. This machine also provides libfluidsynth and a
TimGM6mb SoundFont; it is a small GM instrument set, not a premium sampled piano.

## Windows development setup

1. Install Python 3.12. Run `setup.bat` from the complete source directory.
2. Run `install_transcription.bat` to install/verify the ONNX model.
3. Install FFmpeg and put it on PATH for audio/video decoding and MP3 encoding.
4. For sampled piano rendering, install a matching native FluidSynth library
   discoverable by pyfluidsynth and select a licensed SF2 using **SoundFont**.
   Without SF2 the application uses an explicitly synthetic pitched preview.
5. Run `launch.bat`. `build_exe.bat` uses `tr1pp.spec` to produce a native folder
   build. A Windows CI recipe is included but **has not been executed here**.
   An installer, signing, native dependency bundling and clean-machine testing
   are outstanding. No Windows EXE compatibility is claimed.

Basic Pitch 0.4.0 has upstream metadata that mandates an older TensorFlow build
on Python 3.12 even though its ONNX inference path does not use it. The installer
explicitly installs the upstream model wheel with `--no-deps` after installing
all ONNX runtime dependencies. TLS/checksum verification remains enabled.
`pip check` consequently reports the unused TensorFlow requirement; this is a
known metadata exception, not evidence that TensorFlow inference was tested.
CoreML/TFLite/TensorFlow warnings from Basic Pitch are expected. Model loading
and inference are tested with ONNX Runtime. The model is general-purpose;
dense piano accuracy requires listening and correction, not confidence claims.

## Connected workflow

- Add local MIDI, audio or video files. Supported HTTPS YouTube/Vimeo URLs can be
  imported singly or through **Batch URLs**; direct media URLs are accepted too.
  Online acquisition currently needs cloud network policy changes and is unverified.
- Choose **Complete sources + bridges**, **A/B/A thematic**, **Layered motifs**,
  or **Call and response**. Set target BPM and plan difficulty. Use
  **Import → analyse → compose** to transcribe recordings and build a shared
  editable project automatically. Per-source errors are reported. Cancellation
  is checked between operations; an in-progress model inference must finish.
- Alternatively double-click a MIDI source to edit it, transcribe one recording,
  or use the retained **Analyze / Generate arrangement** MIDI workflow.
- The piano roll supports double-click creation, drag movement, edge resize,
  marquee and Shift selection, cut/copy/paste, Delete, arrows, transpose,
  quantisation, humanisation, velocity, sustain, tempo and undo/redo. Other tracks
  appear as ghost notes. Ctrl+wheel zooms; Alt+wheel adjusts selected velocities.
  The track picker selects the editable hand/track. **Split hands** is a pitch
  heuristic, not learned fingering analysis.
- Timeline ruler clicks seek. Track lanes select a track and can be dragged to
  move its MIDI events. Add absolute-time markers with **Add marker**.
- The mixer controls volume, equal-power pan, mute/solo, graphical gain automation
  and offline low-pass/delay/artificial-room effects. Preview and rendered audio
  use the same mixer. Device selection, pause, seek and loop controls use Qt.
- **Compare bridges** regenerates three technical candidates for a selected
  bridge. Audition them, then apply a chosen bridge as one undoable region edit.
  This preserves outside note fragments. Controller data remains unchanged.
- Save a portable `.tr1pp` project containing exact editable track events, global
  MIDI, source media, settings, mixer, markers and analysis. Source checksums are
  validated on open. Empty tracks and exact note timing survive project saves.
  Recovery snapshots run every 60 seconds after changes; **Recover** opens them.
  Saves retain bounded history under the application data directory.
- Export MIDI, WAV, FLAC, MP3, MusicXML or one WAV per MIDI track. SF2 rendering
  requires the native library and your instrument. MusicXML is approximate
  quantised notation, not a verified engraved piano score.

## Headless workflow

```bash
python -m tr1pp doctor
python -m tr1pp build song-a.wav song-b.mid --project session.tr1pp \
  --cache-dir /workspace/tr1pp-state/cache --structure 'A/B/A thematic' \
  --bpm 110 --midi arrangement.mid
python -m tr1pp render session.tr1pp mix.flac --soundfont piano.sf2
python -m tr1pp analyse arrangement.mid
python -m tr1pp transcribe recording.wav --output-dir /workspace/tr1pp-state/transcriptions
```

Use the environment's Python executable or activate its virtual environment.
`build` exits 2 if it saved a usable project with some failed sources, 1 on
failure and 0 on full success. Models/assets are not fetched during inference.
Optional JSON structure plans can set excerpts, beat placements, transpositions,
repeats and gains in the GUI. Planning is deterministic and source-derived;
no generative neural composer, arbitrary-note "AI", or listening-quality promise.

## Validation

```bash
QT_QPA_PLATFORM=offscreen TR1PP_TEST_MODEL=1 python -m pytest -q
python tools/benchmark.py
```

Omit `TR1PP_TEST_MODEL=1` to skip the two real-model tests. They use generated
music, not commercial recordings. No device playback or Windows build is
validated by passing Linux offscreen tests. See [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)
and [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for remaining limits and test evidence.
