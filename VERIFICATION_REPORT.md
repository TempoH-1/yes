# Verification — TR1PP Mashup Studio 2.0 development checkpoint

This report describes observed capabilities in Linux/Python 3.12. It does not
certify a complete professional application or a Windows executable.

## What was executed

The original 13 regression tests passed before redevelopment. They remain in
place. New integration tests exercise actual editor mutations, piano-roll mouse
and keyboard actions, automatic workflow, candidate comparison/application/undo,
source identity across project reload, mixer, gain automation, effect signal
changes, portable/corrupt project behavior and export codecs.

Two opt-in tests execute the installed Basic Pitch ONNX model against generated
audio, without mocks or inference-time downloads. They verify expected pitches
and onset proximity, cached MIDI reuse, editable output, portable project saving,
rendered output, silent input rejection, and audio-plus-MIDI arrangement. Passing
these generated examples does not establish quality on dense commercial piano.

The current native checks also exercise a real FluidSynth/TimGM6mb SF2 render and
MusicXML export/reimport. Audio codec tests inspect nonzero stereo WAV, FLAC and
MP3 data; MP3 requires FFmpeg. The GUI preview test inspects an actual rendered
file and the Qt player's source. It cannot verify speaker output on this machine.

The final suite passed 61 tests with zero failures or skips. The fresh virtual
environment passed all 59 tests present before the last two media tests were added.
Final command/results are recorded in TEST_RESULTS.txt. Setup is additionally
exercised both idempotently and in a fresh Python virtual environment. The
Linux dependency lock excludes only the editable project and the separately
installed Basic Pitch model wheel; all ONNX dependencies are pinned.

## Capability matrix

| System | Implemented and exercised | Still outstanding |
|---|---|---|
| Import | Local audio/video decode, streaming waveform, source preview source assignment, batch import service, URL validation and per-source error reporting | Real online media acquisition blocked by egress proxy; provider search remains browser-based; download cancellation/progress needs work |
| Transcription | Installed pretrained Basic Pitch ONNX model, mono preprocessing, duration/silence bounds, pitch/length/activation filtering, cache, MIDI, hand heuristic, downstream arrangement | Dedicated piano model, pedal transcription, dense piano corpus evaluation, calibrated confidence, multiple backends |
| Musical analysis | Existing key/phrase/motif analysis plus duration-weighted bar triad labels and inspectable coverage | Robust chord changes/modulation, learned thematic analysis, counterpoint and musical form evaluation |
| Arrangement | Existing source-preserving bridges, editable A/B/A/layered/call-response plans, excerpts/repeats/tempo/transposition/gain, difficulty reduction, candidate audition/region replacement | Neural composition, sophisticated style synthesis, chord-aware layered alignment, local tempo ramps and listening validation |
| Piano editor | Create/move/resize/marquee/cut/copy/paste/delete/transpose/velocity/quantise/humanise, sustain/tempo, bounded undo/redo, ghost tracks, hand split, zoom/scroll | Velocity lane, expression curves, fingering, score-linked editing, multi-track selections and richer tools |
| DAW | MIDI timeline, track move/selection, markers, mixer, pan, mute/solo, gain curve, offline effects, shared preview/export | Editable audio clips, recording, plugin hosting, full automation types, sample-accurate streaming engine |
| Playback | Real SoundFont file rendering, synthetic fallback, Qt transport wiring/seek/loop/device selection, source/candidate audition file assignment | Hardware output/device switching, realtime low latency, premium piano quality and Windows audio verification |
| Project/export | Self-contained atomic project files, exact track events/empty tracks, source checksums, legacy load, recovery/history, MIDI/WAV/FLAC/MP3/stems/MusicXML | Large-asset streaming, score engraving, interoperability corpus, signed projects and unified session undo |
| Windows product | Python 3.12 scripts, PyInstaller spec with ONNX model data, Windows CI recipe | Native execution, installer/signing, native library/tool bundling, clean-machine and device testing |
| Quality | Retained regression suite, real-model/GUI/service/export integrations, reproducible benchmark and setup check | Real music listening/references, crash-injection campaign, long-session stress, Windows runner results |

No row is a claim of complete specification coverage.

## Reproducible observations

`docs/benchmark.json` records this machine's measured 6,133-note, 286.7-second
fixture workload: arrangement about 1.86s, 500-note group edit about 0.028s,
portable save about 0.189s, reload about 0.070s and 8kHz synthetic stereo rendering
about 1.02s. These are observations, not hardware-independent targets or evidence
of musical quality. `tools/benchmark.py` reproduces the workload.

A manual real-model run produced 120 notes with mean model activation about
0.673 from an existing synthetic fixture rendered to audio. Activation is not a
correct-note probability. The focused model tests instead assert recovery of
specified pitches and onset proximity.

An actual YouTube metadata request through yt-dlp failed at the cloud proxy:
`Tunnel connection failed: 403 Forbidden`. This establishes a network restriction,
not missing GitHub authentication or a successful provider integration. The
initial empty GitHub remote was readable with existing injected authentication.

The initial PySide6 6.12 GUI smoke test crashed in the headless multimedia stack.
Pinning PySide6 6.8.3 restored offscreen startup and passed the GUI checks. No TLS,
package signature or artifact verification was disabled during troubleshooting.

`pip check` reports Basic Pitch's unused TensorFlow dependency in this explicit
ONNX-only installation. It is documented in README.md; the actual model path is
loaded and exercised. CoreML/TFLite/TensorFlow backend absence and upstream
resampy/audioread deprecations are expected warnings, not skipped model inference.

## Persistence and publication

Source files and checkpoint notes are in `/workspace/yes`; the repository had no
commits before upload, and no code has been pushed to GitHub. Local files are
present, but remote main restoration is not established. Reusable cloud setup
and start instructions are saved separately in environment settings when that
save succeeds. A draft save does not apply network changes, publish a snapshot
or validate restoration in a new cloud task. Review/save/publish are user actions.

Historical v1.1 reports remain in `docs/history/`. Outstanding work and known
restrictions are explicit in KNOWN_ISSUES.md and DEVELOPMENT_CHECKPOINT.md.

## Saved cloud configuration

The draft save returned `status: saved` and `requires_publish: true`. Fields saved:
`install_script`, `start_skill`, and custom `network.allowed_domains`. The existing
package-manager network preset was preserved. Added custom domains:

- `youtube.com`, `*.youtube.com`, `youtu.be`, `youtubei.googleapis.com`
- `*.googlevideo.com`, `*.ytimg.com`
- `vimeo.com`, `*.vimeo.com`, `*.vimeocdn.com`

These are draft settings. They have not applied to the running proxy, and no
post-change URL success or published/fresh-task restoration is claimed. Review
and save the changes in environment settings, then publish the environment to
retain the prepared filesystem snapshot.

`docs/studio-checkpoint.png` is an offscreen Linux screenshot of the implemented
interface with generated fixture MIDI, not evidence of Windows execution.
