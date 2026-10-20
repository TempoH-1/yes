# TR1PP Mashup Studio 1.1 — reproducible verification

## Environment and evidence

Python Linux runner. Tests executed as `python -m pytest -q -ra`; result in `TEST_RESULTS.txt`. Core PySide6, yt-dlp, basic_pitch, music21 missing in this runner; hence GUI, online and heavy model flows cannot be claimed tested. Source fixtures `tests/fixtures/complex_generated_a.mid` and `complex_generated_b.mid` are *generated*, not original copyrighted transcriptions. MIDI preview was rendered by the prior v1.0 suite using a synthetic sine-wave generator, **not** a sampled acoustic piano.

| Feature | Implementation / actual location | Test result | Evidence | Remaining limitations |
|---|---|---|---|---|
| MIDI import and recovery | Partial: `engine.load`, `midi_repair.recover_midi` | Pass | `test_import_recovery.py`, `test_engine.py` | Original user MIDI not available for tests |
| Multi-source loading | Partial: `engine.arrange` | Pass | `test_full_pipeline` | MIDI-first only |
| URL validation | Partial: `imports.validate_url` | Pass | `test_capabilities.py` | No network exercised |
| YouTube metadata/import | Partial: `imports.metadata`, `imports.acquire` | Not run | yt-dlp unavailable | Site permissions/FFmpeg/availability dependent |
| Integrated title search | Partial: `gui.search_song` | Not run | source inspection | Opens browser; not a catalog |
| Audio/video import | Partial: `imports.extract_local_audio` | Not run | source inspection | FFmpeg runtime unavailable |
| Polyphonic transcription | Partial: `imports.transcribe_audio` | Not run | Basic Pitch missing | No accuracy/confidence/piano-specific model validation |
| MIDI key/tempo statistics | Partial: `engine.analyse` | Pass | `test_full_pipeline` | Estimators not compared to annotated ground truth |
| Phrase boundaries | Partial: `music_theory.phrase_windows` | Pass | `test_phrase_silence_boundary` | Gap-based candidates, not true phrase segmentation |
| Repeated motifs | Partial: `music_theory.motif_signatures` | Pass | `test_repeated_motif_extraction` | Simplified single upper onset voice |
| Chord/function/emotion analysis | Missing | Not run | No corresponding implementation | Requires dedicated models/algorithms |
| AI arrangement generation | Missing | Not run | Heuristic only in `engine._make_bridge` | No trained music-generation AI |
| Transition generation | Partial: `engine._make_bridge` | Pass | `test_full_pipeline`, `test_preserved_source_note_events_and_bridge` | No listening quality verification |
| Candidate scoring | Partial: `quality_metrics.candidate_score` | Pass | `test_quality_diagnostics_detect_collisions_and_leaps` | Heuristic error indicator, not taste rating |
| Source recognisability/preservation | Partial: `engine.arrange` source_regions | Pass | `test_preserved_source_note_events_and_bridge` | >99% event triplets present with strict/humanize disabled, not melody identity |
| Seamless Transition | Partial: `engine.arrange` | Pass | `test_full_pipeline` | Direct musical continuity not verified |
| Full mashup / Classical / Cinematic / Romantic / Minimalist | Missing | Not run | No distinct dedicated algorithms | GUI labels should not imply completion |
| Jazz / Ragtime / Virtuoso | Partial: `engine._make_bridge` | Not separately run | Source inspection | Minor variations, not developed genres |
| Strict two-hand feasibility | Partial: `engine._separate_hands` | Pass | core tests | Pitch split and note filters are not physical fingering |
| Humanisation / sustain | Partial: `engine._humanize`, `engine.arrange` | Pass in existing suite | synthetic MIDI paths | No real human performance calibration |
| Dialog-based piano-roll note edits | Partial: `editing.MidiEditor`, `gui.edit_*` | Pass editor backend | `test_full_pipeline`, `test_failed_edit_does_not_pollute_undo` | GUI interaction not run; no drag-and-drop |
| Undo/redo/paste/pedal | Partial: `editing.MidiEditor` | Pass basic undo/redo | `test_full_pipeline` | Advanced edit workflow not exercised |
| Multitrack waveform/automation editor | Missing | Not run | No implementation | No full DAW editor |
| MIDI preview rendering | Partial: `preview.render_preview` | Pass | `test_full_pipeline` WAV created | Synthetic sound, no realistic piano |
| GUI playback | Partial: `gui.play_preview` | Not run | PySide6 unavailable | No device/latency validation |
| Audio mixer/effects/ASIO | Missing | Not run | No implementation | Not implemented |
| MIDI export/reimport | Partial: `pretty_midi.write` via GUI and editing | Pass | `test_full_pipeline`, `test_preserved_source_note_events_and_bridge` | Windows path/GUI integration unverified |
| Individual hand-track MIDI export | Partial: `editing.MidiEditor.export_hand` | Pass | `test_capabilities.py` | Voice separation heuristic |
| WAV/MP3/FLAC from SoundFont | Partial: `engine.render_audio` | Not run | FluidSynth/FFmpeg unverified | Requires SF2 and dependencies |
| MusicXML import/export / score | Partial export only: `engine.export_musicxml` | Not run | music21 unavailable | No editable notation GUI |
| Project save/reopen/autosave | Partial: `gui.save_project`, `gui.open_project` | Not run | Source inspection | Sidecar MIDI and absolute paths; no autosave |
| Async GUI/error messages | Partial: `gui.Worker`, `gui.work` | Not run | PySide6 unavailable | No cancellation, tracebacks in log |
| Windows EXE/installer | Missing executable: `build_exe.bat` only | Not run | Linux environment | **Not verified on Windows** |
| Linux import/static compile | Complete for included Python sources | Pass | `compileall` | Does not prove runtime GUI support |

## End-to-end test boundary

`tests/test_end_to_end.py::test_full_pipeline` covers two larger synthetic MIDI inputs → analyse → generate 3 bridge candidates → render synthetic WAV → edit/undo/redo → export MIDI → reimport and validate note events. `tests/test_theory_and_preservation.py::test_preserved_source_note_events_and_bridge` checks actual source note triplets at their output offsets (rather than only pitch classes) and nonempty bridge notes. It does **not** prove good music, original themes, expressive playing, quality of AI output, or Windows GUI readiness.
