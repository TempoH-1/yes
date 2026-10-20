# 2.0 continuing development checkpoint (not a release)

Integrated pretrained ONNX transcription, automatic import-to-project workflow,
editable piano roll, source-excerpt structure plans, bridge audition/replacement,
MIDI timeline, stereo mixer, graphical automation/effects, shared render/export,
portable projects, snapshots and headless CLI. Added tested cloud setup, benchmark,
and an unexecuted Windows CI/build recipe. See DEVELOPMENT_CHECKPOINT.md.

The following earlier entries are retained as historical context.

# Changelog — development verification build 1.1 (relative to v1.0)

- Added `tr1pp/music_theory.py`: inspectable MIDI phrase-boundary candidates ranked using note-onset gaps/register changes, and repeated transposition-invariant interval/rhythm motifs.
- Added `tr1pp/quality_metrics.py`: candidate bridge diagnostics for onset gaps, unison collisions, close dissonances, and large melodic leaps; incorporated into comparison scoring.
- Improved bridge motif extraction to use possible phrase boundaries where available rather than always taking a fixed first/last segment.
- Fixed copying the originals using an accurately measured source duration rather than a rounded two-decimal duration (which could trim last notes).
- Added source region boundaries to reports and automated original note-event preservation checks using pitch/onset/offset triples.
- Added four verification tests including repeated motifs, phrase silence, source material preservation on two larger generated sources, and collision/leap diagnostics.
- Existing Windows GUI controls and optional import/transcription paths are preserved, NOT upgraded or reverified in this build.
