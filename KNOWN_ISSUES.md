# Current limits — TR1PP Mashup Studio 2.0 development

## Confirmed environment restrictions

- Online URL inspection/acquisition: a real yt-dlp YouTube metadata request was
  rejected by the cloud egress proxy (HTTP 403 tunnel denial). No token was
  requested. Network domain changes need applying in environment settings before
  another meaningful online test. Arbitrary direct media hosts require their own
  allowlist entries. No URL import success is claimed.
- Linux cloud has no PulseAudio output device. Qt source loading, seeking and
  rendered files are testable; actual speaker output/device switching is not.
- Windows execution/build/installer/signing/clean-machine behavior is untested.
  CI/build files are recipes, not an existing verified Windows deliverable.

## Product and musical limits

- Basic Pitch is a real pretrained general-purpose model, not a dedicated
  state-of-the-art piano transcriber. Rapid dense polyphony, pedal, accents and
  velocities need human correction. Model note activation is uncalibrated.
  No source separation, alternative piano model, or real-song benchmark yet.
- Structural plans operate on real source excerpts with uniform tempo scaling,
  global transposition and a deterministic note-reduction filter. Global key
  alignment does not make layered local chords compatible. Difficulty is not a
  pianist feasibility guarantee. There is no neural composition/LLM arranger.
- Existing named style modes have limited bass/ornament differences. The legacy
  overlap target remains explicitly planned; the default engine appends bridges
  and preserves complete songs, rather than implementing real audio crossfades.
- Timeline lanes contain MIDI notes, not independently editable audio clips.
  Source waveform inspection/playback is separate. No live audio recording,
  plugin hosting, MIDI device recording, audio-clip stretch/cut editing, or
  sample-accurate real-time DAW engine yet.
- Synthetic preview has no drum kit or realistic sustain. FluidSynth/SF2
  rendering supports the MIDI controllers. Offline effects are simple DSP,
  not a commercial mixing/mastering suite. No subjective listening verification
  of sampled piano quality has been performed.
- The piano roll edits one active track with ghosted other tracks. It lacks
  per-note expression curves, score-linked editing and a velocity-lane graph.
  Selection and MIDI note/controller edits support undo; mixer/marker/settings
  changes use project snapshots rather than the MIDI undo stack.
- Changing the initial tempo scales the complete MIDI tempo map and events.
  User markers are absolute-time anchors; they do not scale with tempo undo.
  Original analysis reports describe generation time, not every subsequent edit.
- Bridge replacement keeps existing controllers and splits crossing note
  fragments. It does not regenerate pedal or optimise boundary phrasing.
- Exported MIDI has MIDI tick resolution and normally loses empty tracks.
  Portable projects additionally retain exact track events and empty tracks.
  MusicXML uses music21 quantisation; notation spelling and engraving need review.

## Reliability and operational bounds

- Projects are limited to 512 MiB uncompressed; larger media must be trimmed
  externally. Rendering/transcription normally allow ten minutes. Source import
  accepts at most 32 inputs per automatic workflow and up to 256 planned clips.
- Rendering allocates bounded full-length arrays and runs in a worker. It is
  offline, not a streaming mixer. Undo snapshots retain at most 60 states and
  approximately one million historical note objects (at least one state).
- Cancellation takes effect between operations; FFmpeg/model calls are not
  forcibly interrupted. Controls are disabled during jobs to prevent stale edits.
- Recovery retains 12 snapshots across projects; per-save history retains 20
  snapshots per saved path. First autosave occurs after 60 seconds of changes.
  Unsaved work before the first snapshot can be lost in a hard crash.
- Invalid/corrupt project writes leave the previous project intact. ZIP size,
  traversal, duplicate-member and source-checksum checks exist, but projects are
  not a hardened untrusted-file sandbox or a signed interchange format.
- Basic Pitch's unused TensorFlow metadata requirement is intentionally unmet
  by the ONNX-only installation; `pip check` reports that exception. resampy
  requires pinned setuptools <81. Other backend warnings are expected.
- PySide6 6.12 crashed in this cloud's headless multimedia stack. The application
  is pinned to 6.8.3, which passed GUI/transport tests. Changing Qt needs regression
  testing. Python 3.12 is the tested interpreter.

Exact continuation work is in DEVELOPMENT_CHECKPOINT.md.
