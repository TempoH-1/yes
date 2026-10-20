"""Inspectable symbolic phrase and motif analysis; does not purport to recognise music as a listener does."""
from collections import Counter
from statistics import median
import math

def phrase_windows(notes, duration, window=4.0):
    """Rank phrase transitions based on onset gaps, coarse register changes and downbeat proximity."""
    if not notes or duration<=0:return []
    onset=sorted(set(round(n.start,3) for n in notes))
    ranked=[]
    for ix in range(1,len(onset)):
        gap=onset[ix]-onset[ix-1]
        if gap<.13:continue
        t=onset[ix]
        if not .6<=t<=duration-.3:continue
        before=[n.pitch for n in notes if t-window<=n.start<t]
        after=[n.pitch for n in notes if t<=n.start<t+window]
        if not before or not after:continue
        change=min(1,abs(median(before)-median(after))/24)
        # Local silence is stronger evidence than a speculative chord boundary.
        score=min(3,gap/.35)+.45*change
        ranked.append((round(score,3),round(t,3)))
    return [{'time':t,'score':score} for score,t in sorted(ranked,reverse=True)[:12]]

def motif_signatures(notes, length=5, min_repeats=2):
    """Exact-transposition-invariant five-note interval motifs and their occurrence counts."""
    sequence=sorted((n for n in notes if n.pitch>=55),key=lambda n:(n.start,-n.pitch))
    # One dominant voice per approximate onset; not a trained melody extractor.
    chosen=[]
    for n in sequence:
        if not chosen or n.start-chosen[-1].start>.07:chosen.append(n)
        elif n.pitch>chosen[-1].pitch:chosen[-1]=n
    freq=Counter()
    for i in range(max(0,len(chosen)-length+1)):
        fragment=chosen[i:i+length]
        if fragment[-1].start-fragment[0].start>12:continue
        intervals=tuple(fragment[k+1].pitch-fragment[k].pitch for k in range(length-1))
        # Rhythm is bucketed relative to median interonset period.
        gaps=[fragment[k+1].start-fragment[k].start for k in range(length-1)]
        beat=max(.01,median(gaps))
        rhythm=tuple(min(8,max(1,round(g/beat*2))) for g in gaps)
        freq[(intervals,rhythm)]+=1
    return [{'intervals':list(a),'relative_rhythm':list(b),'occurrences':num} for (a,b),num in freq.most_common(10) if num>=min_repeats]
