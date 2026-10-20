"""Transactional MIDI editing with bounded snapshot history and event preservation."""
from __future__ import annotations
import copy
import math
import pretty_midi

class MidiEditor:
    def __init__(self, midi, limit=60):
        if limit < 1: raise ValueError('Undo limit must be positive')
        self.pm=copy.deepcopy(midi)
        self.undo_stack=[]; self.redo_stack=[]; self.limit=limit

    def _snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.pm))
        self.undo_stack=self.undo_stack[-self.limit:]
        # Avoid retaining millions of dense note objects across sixty full copies.
        total=sum(sum(len(i.notes) for i in pm.instruments) for pm in self.undo_stack)
        while len(self.undo_stack)>1 and total>1_000_000:
            total-=sum(len(i.notes) for i in self.undo_stack.pop(0).instruments)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:return False
        self.redo_stack.append(self.pm);self.pm=self.undo_stack.pop();return True

    def redo(self):
        if not self.redo_stack:return False
        self.undo_stack.append(self.pm);self.pm=self.redo_stack.pop();return True

    def _track(self,track):
        if not isinstance(track,int) or not 0<=track<len(self.pm.instruments):raise IndexError('Track not found')
        return self.pm.instruments[track]

    def _indices(self,track,indices):
        ins=self._track(track);indices=sorted(set(indices))
        if any(not isinstance(i,int) or not 0<=i<len(ins.notes) for i in indices):raise IndexError('Note not found')
        return ins,indices

    @staticmethod
    def _finite(*values):
        if not all(math.isfinite(float(v)) for v in values):raise ValueError('Edit values must be finite')

    def add(self,track,pitch,start,length,velocity=80):
        ins=self._track(track);self._finite(pitch,start,length,velocity)
        if length<=0:raise ValueError('Length must be positive')
        start=max(0,float(start))
        note=pretty_midi.Note(int(max(1,min(127,velocity))),int(max(0,min(127,pitch))),start,start+float(length))
        self._snapshot();ins.notes.append(note);return len(ins.notes)-1

    def delete(self,track,index):
        self.delete_many(track,[index])

    def change(self,track,index,**props):
        ins,_=self._indices(track,[index]);n=ins.notes[index]
        pitch=props.get('pitch',n.pitch);start=props.get('start',n.start)
        end=props.get('end',n.end);velocity=props.get('velocity',n.velocity)
        self._finite(pitch,start,end,velocity)
        start=max(0,float(start));end=max(start+.01,float(end))
        self._snapshot()
        n.pitch=int(max(0,min(127,pitch)));n.start=start;n.end=end;n.velocity=int(max(1,min(127,velocity)))

    def transform(self,track,indices,transpose=0,quantize=0,velocity_delta=0,time_delta=0):
        ins,indices=self._indices(track,indices)
        self._finite(transpose,quantize,velocity_delta,time_delta)
        if quantize<0:raise ValueError('Quantisation grid must not be negative')
        if not indices:return
        self._snapshot()
        for ix in indices:
            n=ins.notes[ix];length=n.end-n.start;start=max(0,n.start+time_delta)
            if quantize>0:
                start=round(start/quantize)*quantize;length=max(quantize/4,round(length/quantize)*quantize)
            n.pitch=int(max(0,min(127,n.pitch+transpose)));n.velocity=int(max(1,min(127,n.velocity+velocity_delta)))
            n.start=start;n.end=start+length

    def pedal(self,track,start,end,on=True):
        ins=self._track(track);self._finite(start,end)
        if start<0 or end<=start:raise ValueError('Pedal end must follow a nonnegative start')
        self._snapshot()
        ins.control_changes.extend([pretty_midi.ControlChange(64,100 if on else 0,start),pretty_midi.ControlChange(64,0,end)])
        ins.control_changes.sort(key=lambda x:x.time)

    def copy_passage(self,track,indices):
        ins,indices=self._indices(track,indices);return copy.deepcopy([ins.notes[i] for i in indices])

    def paste_passage(self,track,notes,at):
        ins=self._track(track);self._finite(at)
        if at<0:raise ValueError('Paste position must not be negative')
        if not notes:return
        prepared=copy.deepcopy(notes);origin=min(n.start for n in prepared)
        for n in prepared:
            self._finite(n.start,n.end,n.pitch,n.velocity)
            length=n.end-n.start
            if length<=0:raise ValueError('Clipboard contains an invalid note')
            n.start=at+n.start-origin;n.end=n.start+length
        self._snapshot();ins.notes.extend(prepared)

    def export_hand(self,track,path):
        ins=self._track(track);result=copy.deepcopy(self.pm)
        result.instruments=[copy.deepcopy(ins)];result.write(str(path))

    def delete_many(self, track, indices):
        indices = sorted(set(indices), reverse=True)
        ins = self._track(track)
        for ix in indices:
            if not 0 <= ix < len(ins.notes): raise IndexError('Note not found')
        if not indices: return
        self._snapshot()
        for ix in indices: del ins.notes[ix]

    def duplicate(self, track, indices, at):
        self.paste_passage(track, self.copy_passage(track, indices), at)

    def humanize(self, track, indices, milliseconds=8, velocity=4, seed=17):
        import random, math
        if not math.isfinite(milliseconds) or not 0 <= milliseconds <= 100:
            raise ValueError('Humanization must be within 0–100 ms')
        ins,indices = self._indices(track,indices)
        if not isinstance(velocity,int) or not 0<=velocity<=127: raise ValueError('Invalid velocity variation')
        if not indices: return
        self._snapshot(); rng = random.Random(seed)
        for ix in indices:
            n = ins.notes[ix]; length = n.end - n.start
            n.start = max(0, n.start + rng.uniform(-milliseconds, milliseconds)/1000)
            n.end = n.start + length
            n.velocity = max(1, min(127, n.velocity + rng.randint(-abs(velocity), abs(velocity))))

    def move_notes(self, track, indices, time_delta=0, transpose=0):
        """Move a selection as a rigid group, retaining relative timing at time zero."""
        ins, indices = self._indices(track,indices)
        self._finite(time_delta,transpose)
        notes = [ins.notes[ix] for ix in indices]
        if not notes: return
        time_delta = max(float(time_delta), -min(n.start for n in notes))
        transpose = max(-min(n.pitch for n in notes), min(int(transpose), 127-max(n.pitch for n in notes)))
        self.transform(track, indices, transpose=transpose, time_delta=time_delta)

    def shift_track(self, track, seconds):
        import math
        ins = self._track(track)
        if not math.isfinite(seconds): raise ValueError('Track offset must be finite')
        events = ins.notes + ins.control_changes + ins.pitch_bends
        if not events: return
        origin = min(n.start for n in ins.notes) if ins.notes else float('inf')
        origin = min([origin]+[e.time for e in ins.control_changes + ins.pitch_bends])
        seconds = max(seconds, -origin)
        self._snapshot()
        for n in ins.notes: n.start += seconds; n.end += seconds
        for e in ins.control_changes + ins.pitch_bends: e.time += seconds

    def add_track(self, name='Piano', program=0):
        if not 0 <= program <= 127: raise ValueError('Invalid MIDI program')
        self._snapshot(); self.pm.instruments.append(pretty_midi.Instrument(program, name=name))
        return len(self.pm.instruments)-1

    def set_tempo(self, bpm):
        """Scale the full MIDI tempo map and all timed events, preserving musical beats."""
        import math
        if not math.isfinite(bpm) or not 20 <= bpm <= 400: raise ValueError('Tempo must be 20–400 BPM')
        times, tempi = self.pm.get_tempo_changes()
        ratio = float(tempi[0]) / bpm
        self._snapshot()
        for ins in self.pm.instruments:
            for n in ins.notes: n.start *= ratio; n.end *= ratio
            for e in ins.control_changes + ins.pitch_bends: e.time *= ratio
        for seq in (self.pm.key_signature_changes, self.pm.time_signature_changes, self.pm.lyrics, self.pm.text_events):
            for e in seq: e.time *= ratio
        self.pm._tick_scales = [(tick, scale*ratio) for tick, scale in self.pm._tick_scales]
        self.pm._update_tick_to_time(len(self.pm._PrettyMIDI__tick_to_time)-1)

    def assign_hands(self, split=60):
        """Pitch-split into two tracks. Preserves source CCs on both resulting tracks."""
        if not 0 <= split <= 127: raise ValueError('Invalid hand split')
        self._snapshot()
        left = pretty_midi.Instrument(0, name='Left Hand')
        right = pretty_midi.Instrument(0, name='Right Hand')
        drums = []
        for ins in self.pm.instruments:
            if ins.is_drum: drums.append(copy.deepcopy(ins)); continue
            for note in ins.notes:
                (left if note.pitch < split else right).notes.append(copy.deepcopy(note))
            for dest in (left, right):
                dest.control_changes.extend(copy.deepcopy(ins.control_changes))
                dest.pitch_bends.extend(copy.deepcopy(ins.pitch_bends))
        for ins in (left, right):
            ins.notes.sort(key=lambda n:(n.start,n.pitch))
            ins.control_changes.sort(key=lambda e:e.time)
            ins.pitch_bends.sort(key=lambda e:e.time)
        self.pm.instruments = [left, right]+drums

    def set_velocities(self, track, indices, value):
        if not 1 <= value <= 127: raise ValueError('Velocity must be 1–127')
        ins=self._track(track); indices=sorted(set(indices))
        for ix in indices: ins.notes[ix]
        if not indices: return
        self._snapshot()
        for ix in indices: ins.notes[ix].velocity=int(value)

    def replace_region(self, start, end, replacement):
        """Replace notes within a time interval as one undoable edit.

        Outside note fragments, existing track controllers and global MIDI
        metadata are retained. Replacement note times are relative to zero.
        """
        import math
        if not all(math.isfinite(v) for v in (start,end)) or start<0 or end<=start:
            raise ValueError('Invalid replacement interval')
        if not self.pm.instruments: raise ValueError('Create a track first')
        prepared=[]
        for ins in replacement.instruments:
            for note in ins.notes:
                if note.start<0 or note.end>end-start+.001: raise ValueError('Replacement extends beyond the region')
                # Prefer named hands in a two-hand arrangement, otherwise track 0.
                name='Left Hand' if note.pitch<60 else 'Right Hand'
                target=next((i for i,t in enumerate(self.pm.instruments) if t.name==name),0)
                copy_note=copy.deepcopy(note);copy_note.start+=start;copy_note.end+=start
                prepared.append((target,copy_note))
        self._snapshot()
        for ins in self.pm.instruments:
            kept=[]
            for note in ins.notes:
                if note.end<=start or note.start>=end:kept.append(note);continue
                if note.start<start:
                    fragment=copy.deepcopy(note);fragment.end=start;kept.append(fragment)
                if note.end>end:
                    fragment=copy.deepcopy(note);fragment.start=end;kept.append(fragment)
            ins.notes=kept
        for index,note in prepared:self.pm.instruments[index].notes.append(note)
        for ins in self.pm.instruments:ins.notes.sort(key=lambda n:(n.start,n.pitch))
