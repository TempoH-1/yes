"""Objective MIDI bridge diagnostics, not aesthetic or AI-generated quality scores."""
from collections import defaultdict
from statistics import median

DISSONANT={1,2,6,10,11}

def bridge_metrics(notes,start,end):
    events=sorted((n for n in notes if start<=n.start<end),key=lambda n:(n.start,n.pitch))
    if not events:
        return {'note_count':0,'empty':True,'unison_collisions':0,'close_dissonances':0,'large_melodic_leaps':0,'max_onset_gap_sec':round(end-start,3)}
    bins=defaultdict(list)
    for n in events:bins[round(n.start/.05)].append(n.pitch)
    duplicates=sum(len(ps)-len(set(ps)) for ps in bins.values())
    close_dissonances=0
    for pitches in bins.values():
        pitches=sorted(set(pitches))
        close_dissonances+=sum(0<q-p<=12 and (q-p)%12 in DISSONANT for i,p in enumerate(pitches) for q in pitches[i+1:])
    melody=[]
    for n in events:
        if n.pitch<55:continue
        if melody and abs(n.start-melody[-1].start)<=.05:
            if n.pitch>melody[-1].pitch:melody[-1]=n
        else:melody.append(n)
    leaps=sum(abs(b.pitch-a.pitch)>12 for a,b in zip(melody,melody[1:]))
    times=sorted(set(round(n.start,4) for n in events))
    gaps=[b-a for a,b in zip(times,times[1:])]
    return {'note_count':len(events),'empty':False,'unison_collisions':duplicates,
       'close_dissonances':close_dissonances,'large_melodic_leaps':leaps,
       'max_onset_gap_sec':round(max(gaps,default=0),3),
       'median_onset_gap_sec':round(median(gaps),3) if gaps else 0}

def candidate_score(notes,start,end,arrival_anchor_count=0):
    m=bridge_metrics(notes,start,end)
    m['objective_proxy_score']=round(2*arrival_anchor_count-2*m['unison_collisions']-.35*m['close_dissonances']-.8*m['large_melodic_leaps']-max(0,m['max_onset_gap_sec']-1)*2,3)
    m['score_warning']='A technical proxy for basic errors; cannot establish harmonic correctness or musical quality.'
    return m
