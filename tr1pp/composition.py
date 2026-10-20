"""Deterministic, source-derived transition planning; not neural composition.
Motif matching, phrase placement, and voice-leading are transparent heuristics.
"""
from __future__ import annotations
import math
import numpy as np
import pretty_midi


def phrase_boundaries(pm, window=1.5):
    notes=sorted((n for ins in pm.instruments if not ins.is_drum for n in ins.notes),key=lambda n:n.start)
    if not notes:return [0.]
    end=max(n.end for n in notes)
    gaps=[(notes[i+1].start-notes[i].end, notes[i+1].start) for i in range(len(notes)-1)]
    b=[0.]+[round(t,3) for gap,t in gaps if gap>max(.32,window*.28)]
    # Include near-measure boundaries when there are no silent gaps (dense piano pieces).
    try:bpm=pm.estimate_tempo()
    except Exception:bpm=120
    bar=240/max(45,min(240,bpm))
    if len(b)<3:
        for i in range(1,int(end/bar)):
            t=i*bar
            if any(abs(n.start-t)<.13 for n in notes):b.append(round(t,3))
    return sorted(set(b+[round(end,3)]))


def extract_motifs(pm,length=3.0,top_k=5):
    notes=sorted((n for ins in pm.instruments if not ins.is_drum for n in ins.notes),key=lambda n:n.start)
    if not notes:return []
    boundaries=phrase_boundaries(pm)
    motifs=[]
    for st in boundaries[:-1]:
        window=[n for n in notes if st<=n.start<st+length]
        if len(window)<3:continue
        # One note per 65 ms onset group: the highest pitch is the provisional melody.
        groups=[]
        for n in window:
            if not groups or n.start-groups[-1][-1].start>.065:groups.append([n])
            else:groups[-1].append(n)
        lead=[max(g,key=lambda n:n.pitch) for g in groups]
        if len(lead)<3:continue
        contour=tuple(max(-7,min(7,lead[i+1].pitch-lead[i].pitch)) for i in range(min(len(lead)-1,11)))
        density=len(lead)/length
        pitch_range=max(n.pitch for n in lead)-min(n.pitch for n in lead)
        score=2*len(set(contour))+min(8,density)+min(12,pitch_range)*.2
        motifs.append({'start':st,'notes':lead[:24],'contour':contour,'score':round(score,2)})
    motifs.sort(key=lambda m:m['score'],reverse=True)
    return motifs[:top_k]


def transition_strategy(mode):
    return {
      'Seamless Transition':'anticipation',
      'Full Mashup':'counterpoint',
      'Classical':'sequential_modulation',
      'Jazz Fusion':'chromatic_approach',
      'Virtuoso Piano':'rhythmic_acceleration',
      'Cinematic':'dynamic_swell',
      'Ragtime':'syncopated_bass',
      'Custom':'anticipation',
    }.get(mode,'anticipation')


def spectral_tension(notes, root):
    # Non-chord pitch classes within a tonic triad; context-dependent approximation only.
    chord={(root+i)%12 for i in (0,3,4,7)}
    return sum(n.pitch%12 not in chord for n in notes)/max(1,len(notes))


def assess_bridge(bridge,root_target,duration):
    notes=bridge.notes
    if not notes:return {'score':-100,'density':0,'clash_estimate':1,'continuity':0}
    density=len(notes)/max(.1,duration)
    clash=spectral_tension(notes,root_target)
    end=[n for n in notes if n.start>max(n.start for n in notes)-duration*.15]
    cadence=sum((n.pitch-root_target)%12 in (0,4,7) for n in end)/max(1,len(end))
    leaps=[]
    mel=sorted((n for n in notes if n.pitch>=60),key=lambda n:n.start)
    for a,b in zip(mel,mel[1:]):
        if b.start-a.start>.04:leaps.append(abs(a.pitch-b.pitch))
    jump=np.mean(leaps) if leaps else 0
    score=3*cadence-1.5*clash-.04*jump-.08*max(0,density-18)
    return {'score':round(float(score),3),'density':round(density,2),'clash_estimate':round(clash,3),'cadence_tone_ratio':round(cadence,3),'mean_melodic_leap':round(float(jump),2),'continuity':round(float(1/(1+jump/12)),3)}
