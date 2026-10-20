# TR1PP Mashup Studio 2.0 development architecture

This is one continuing development tree imported from the supplied v1.1 archive.
It is not a completed 2.0 release.

Retain `engine`, `music_theory`, `composition`, `quality_metrics`, and `midi_repair`
for the existing source-preserving symbolic arrangement behavior. Keep its
heuristic claims explicit. Expand `editing` into transactional note/track edits.
Replace the display-only piano roll with an interactive editor. Replace project
JSON plus absolute sidecar MIDI with an atomic, portable project container.

The connected workflow is source acquisition -> decoded audio -> pretrained
transcription -> MIDI analysis/arrangement -> shared editable MIDI -> timeline,
mixer, playback and export -> portable project and recovery snapshot.

* `project`: versioned portable storage, validated mixer metadata and assets;
  transactional writes and bounded, validated reads. No executable serialization.
* `editing`: undoable MIDI mutations, selection operations, tempo and hand tools.
* `transcription`: installed Basic Pitch model discovery, preprocessing,
  confidence-bearing notes, filtering, cache and source-linked result metadata.
* `audio`: shared stereo render for preview/export; per-track volume/pan,
  mute/solo, gain automation, optional SoundFont and explicit synthetic fallback.
* `widgets`: editor and timeline views emitting edits rather than owning MIDI.
* `gui`: asynchronous work, session binding, playback transport, project/recovery.

The application owns a single editor MIDI snapshot. Every edit rebinds all views
and invalidates rendered playback. Background jobs must retain their thread
objects and reject overlapping jobs. GUI writes happen on the GUI thread.

Validation layers: retained regression suite; editor/storage/render tests;
actual pretrained-model audio roundtrip; offscreen Qt interaction tests; complete
source -> arrangement -> edit -> save/reopen -> render/export integration.
Windows native audio devices and EXE behavior require a Windows runner. Commercial
quality transcription/composition and arbitrary recordings require a real music
corpus and listening evaluation, beyond synthetic fixture tests.
