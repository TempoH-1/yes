# Known issues and missing capabilities

1. No genuinely trained generative composition/arrangement model or calibrated listener evaluation. Bridge remains a transparent heuristic using actual source motifs.
2. Phrase-boundary and melody inference is onset/pitch-statistics based; it can misidentify phrases in polyphonic textures, ornaments or long sustained passages.
3. Named GUI arrangement modes other than a few bridge embellishments are largely placeholders and must not be considered distinct fully implemented style engines.
4. URL metadata/download requires yt-dlp, actual supported site access, sufficient permissions and FFmpeg; not network-tested here. Search by title still launches a web browser, not an integrated catalog.
5. Basic Pitch is an optional unverified backend and is poorly suited for dense overlapping piano; no specialised piano model was integrated.
6. GUI PySide6 not installed in this Linux runner; GUI launch, Qt audio playback, mouse editing and Windows compatibility NOT verified. Editing controls remain dialog-based.
7. No comprehensive timeline, waveform editor, mixer, effects, SoundFont library, ASIO, AI natural-language instructions, section regeneration, audio source separation, source caching or automatic refining system.
8. MIDI original source provenance test runs with `strict_two_hands=False` and humanisation disabled; the strict filter intentionally removes some notes.
9. Quality scores are diagnostics, not subjective musical-quality scores. The generated examples have not been evaluated by listening.
10. EXE build script is present, but no Windows executable was compiled or executed here.
11. MusicXML, compressed audio import and audio export depend on external optional programs and were not executed in this build.
