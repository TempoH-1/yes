from pathlib import Path
import pretty_midi
from tr1pp.music_theory import motif_signatures,phrase_windows
from tr1pp.engine import arrange,Settings,load,all_notes

F=Path(__file__).parent/'fixtures'

def test_repeated_motif_extraction():
    notes=[]
    for offset in (0,3,6):
        for k,pitch in enumerate((60,62,64,65,67,69)):
            notes.append(pretty_midi.Note(90,pitch,offset+k*.25,offset+k*.25+.2))
    patterns=motif_signatures(notes)
    assert any(x['intervals']==[2,2,1,2] and x['occurrences']>=3 for x in patterns)

def test_phrase_silence_boundary():
    notes=[]
    for offset in (0,3):
        for k in range(8):notes.append(pretty_midi.Note(80,60+k%4,offset+k*.2,offset+k*.2+.1))
    result=phrase_windows(notes,5)
    assert any(abs(x['time']-3)<.001 for x in result)

def test_preserved_source_note_events_and_bridge():
    paths=[F/'complex_generated_a.mid',F/'complex_generated_b.mid']
    originals=[load(p) for p in paths]
    result,report=arrange(paths,Settings(bridge_bars=3,humanize_ms=0,strict_two_hands=False))
    output=all_notes(result)
    for src,region in zip(originals,report['source_regions']):
        offset=region['start']
        # Original events must appear at their actual pitch/time, not just share pitch classes.
        output_set={(n.pitch,round(n.start,3),round(n.end,3)) for n in output}
        original=all_notes(src)
        present=sum((n.pitch,round(n.start+offset,3),round(n.end+offset,3)) in output_set for n in original)
        assert present/len(original)>.99
    t=report['transitions'][0]
    assert any(t['start']<=n.start<t['end'] for n in output)
    assert len(report['sources'][0]['phrase_boundary_candidates'])>0

def test_quality_diagnostics_detect_collisions_and_leaps():
    from tr1pp.quality_metrics import bridge_metrics
    xs=[pretty_midi.Note(80,60,0,.2),pretty_midi.Note(80,60,0,.2),
        pretty_midi.Note(80,61,0,.2),pretty_midi.Note(80,90,.5,.7)]
    metrics=bridge_metrics(xs,0,1)
    assert metrics['unison_collisions']>=1
    assert metrics['close_dissonances']>=1
    assert metrics['large_melodic_leaps']>=1
