# TR1PP Mashup Studio — 1.1 verification development build

**Not a complete professional DAW or autonomous music arranger.** This package extends the actual v1.0 source archive, preserving the original PySide6 interface, adding inspectable symbolic analysis and bridge diagnostics.

## Windows start

1. Install Python 3.11 or a version compatible with the selected dependencies. Unzip the complete directory.
2. Run `setup.bat`, then `launch.bat` from the project directory.
3. Add at least two actual MIDI files, select their order, click **Analyze**, then **Generate arrangement** and **Export MIDI**.
4. Audio/video: paste a supported URL in the top bar, choose **Inspect URL**, then **Import URL audio** (requires yt-dlp and FFmpeg). Select the downloaded audio and **Transcribe selected audio** (requires optional Basic Pitch). This online workflow is not verified in this release.
5. Optionally use `install_transcription.bat` on a compatible Python installation; check installed Basic Pitch support. The best accuracy for dense piano music is obtained from actual MIDI sources, not this transcription backend.
6. `build_exe.bat` is an *unverified Windows build recipe*, not a precompiled EXE.

## Tests

From the project directory: `python -m pytest -q`. Test fixture MIDI is synthetic; it does not contain the original Rush E or Entry of the Gladiators recordings. See `VERIFICATION_REPORT.md` and `TEST_RESULTS.txt`.

## What the bridge engine really does

It identifies potential phrase boundaries and repeated symbolic note patterns, pulls note material from both source MIDIs, constructs three variant bridges and scores limited technical properties. Original note content is placed sequentially with constructed bridge regions in between. It is **not** sophisticated artificial-intelligence composition or a quality guarantee; the distinct style modes are not yet complete.

## Deliverables

`tr1pp/` implementation, `tests/` runnable suite, `examples/` prior generated demonstration, `requirements.txt`, Windows scripts, `TEST_RESULTS.txt`, `VERIFICATION_REPORT.md`, `KNOWN_ISSUES.md` and `CHANGELOG.md`.
