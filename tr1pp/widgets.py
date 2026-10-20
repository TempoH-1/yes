"""Interactive MIDI editor and arrangement timeline, sharing the session editor."""
from __future__ import annotations
import math
import bisect
import pretty_midi
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import QWidget, QSizePolicy

COLORS = ['#dfa864', '#5bbbe8', '#8bd3a8', '#bb9fe8', '#eb8195', '#88aaff']

class PianoRoll(QWidget):
    changed = Signal()
    selectionChanged = Signal(object)
    seekRequested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pm = None; self.editor = None; self.track = 0; self._note_cache = {}
        self.selection = set(); self.clipboard = []; self.pixels_per_second = 85.
        self.row_height = 13; self.gutter = 64; self.ruler = 25
        self.grid = .25; self.cursor = 0.; self._drag = None; self._preview = None; self._marquee = None
        self.setFocusPolicy(Qt.StrongFocus); self.setMouseTracking(True)
        self.setToolTip('Double-click: add · Drag: move · Drag right edge: resize · Shift-click: select multiple · Delete · Ctrl+C/V · Arrow keys · Alt+wheel: velocity')
        self._size()

    def bind(self, editor, track=0):
        if editor is not self.editor: self.selection.clear()
        self.editor = editor; self.track = track; self.set_midi(editor.pm if editor else None)

    def set_midi(self, pm):
        self.pm = pm
        self._note_cache={}
        if pm is not None:
            for track,ins in enumerate(pm.instruments):
                order=sorted(range(len(ins.notes)),key=lambda ix:ins.notes[ix].start)
                self._note_cache[track]=(order,[ins.notes[ix].start for ix in order],max((n.end-n.start for n in ins.notes),default=0))
        self.selection = {i for i in self.selection if i < len(self.notes())}
        self._size(); self.update()

    def notes(self):
        if self.pm is None or not 0 <= self.track < len(self.pm.instruments): return []
        return self.pm.instruments[self.track].notes

    def _size(self):
        duration = self.pm.get_end_time()+4 if self.pm else 12
        self.setMinimumSize(max(850, int(self.gutter+duration*self.pixels_per_second)), 128*self.row_height+self.ruler)
        self.resize(self.minimumSize())

    def zoom(self, factor):
        self.pixels_per_second = max(15, min(500, self.pixels_per_second*factor)); self._size(); self.update()

    def note_rect(self, note):
        return QRectF(self.gutter+note.start*self.pixels_per_second,
                      self.ruler+(127-note.pitch)*self.row_height,
                      max(4., (note.end-note.start)*self.pixels_per_second), self.row_height-1)

    def time_at(self, x): return max(0., (x-self.gutter)/self.pixels_per_second)
    def pitch_at(self, y): return max(0, min(127, 127-int((y-self.ruler)//self.row_height)))
    def snap(self, seconds): return round(seconds/self.grid)*self.grid if self.grid else seconds

    def visible_notes(self,track,left,right):
        if self.pm is None or track not in self._note_cache:return []
        order,starts,max_length=self._note_cache[track]
        lo=bisect.bisect_left(starts,max(0,left-max_length));hi=bisect.bisect_right(starts,right)
        return ((index,self.pm.instruments[track].notes[index]) for index in order[lo:hi])

    def hit(self, pos):
        time=self.time_at(pos.x())
        for index,note in reversed(list(self.visible_notes(self.track,time-.05,time+.05))):
            if self.note_rect(note).contains(pos):return index
        return None

    def paintEvent(self, event):
        p = QPainter(self); p.fillRect(event.rect(), QColor('#111a29'))
        visible = event.rect(); rh = self.row_height
        for pitch in range(128):
            y = self.ruler+(127-pitch)*rh
            if y+rh < visible.top() or y > visible.bottom(): continue
            black = pitch%12 in (1,3,6,8,10)
            p.fillRect(0,y,self.width(),rh,QColor('#151f30' if black else '#1b283b'))
            p.fillRect(0,y,self.gutter-1,rh,QColor('#24324b' if black else '#cad5df'))
            if pitch%12 == 0 or rh >= 16:
                p.setPen(QColor('#8ba1b7' if black else '#1b283b'))
                p.drawText(3,y+rh-2, pretty_midi.note_number_to_name(pitch))
            p.setPen(QColor('#2b394d')); p.drawLine(self.gutter,y,self.width(),y)
        step = self.grid or .5
        while step*self.pixels_per_second < 15: step *= 2
        first = max(0, int((visible.left()-self.gutter)/(step*self.pixels_per_second)))
        last = int((visible.right()-self.gutter)/(step*self.pixels_per_second))+1
        for k in range(first, last+1):
            x = self.gutter+k*step*self.pixels_per_second
            p.setPen(QColor('#354961' if k%4 == 0 else '#24334a')); p.drawLine(int(x),0,int(x),self.height())
            if k%4 == 0:
                p.setPen(QColor('#b6c8de')); p.drawText(int(x)+3,17,f'{k*step:g}s')
        # Ghost other tracks so both hands remain visible while one track is edited.
        if self.pm is not None:
            for track,ins in enumerate(self.pm.instruments):
                if track==self.track:continue
                for _,note in self.visible_notes(track,self.time_at(visible.left()),self.time_at(visible.right())):
                    rect=self.note_rect(note)
                    if rect.intersects(QRectF(visible)):
                        color=QColor(COLORS[track%len(COLORS)]);color.setAlpha(45);p.fillRect(rect,color)
        for index,n in self.visible_notes(self.track,self.time_at(visible.left()),self.time_at(visible.right())):
            r = self.note_rect(n)
            if self._preview and index in self.selection:
                dx,dy=self._preview
                if self._drag and self._drag[2]=='resize':
                    if index==self._drag[1]:r.setWidth(max(3,r.width()+dx*self.pixels_per_second))
                else:r.translate(dx*self.pixels_per_second,-dy*self.row_height)
            if not r.intersects(QRectF(visible)): continue
            color = QColor(COLORS[self.track%len(COLORS)]); color.setAlpha(95+int(n.velocity))
            p.fillRect(r, color)
            p.setPen(QPen(QColor('#ffffff' if index in self.selection else '#527084'), 2 if index in self.selection else 1))
            p.drawRect(r)
            if r.width() > 48 and rh >= 13:
                p.setPen(QColor('#12202d')); p.drawText(r.adjusted(3,0,-1,0), Qt.AlignVCenter, pretty_midi.note_number_to_name(n.pitch))
        if self._marquee:
            p.setPen(QPen(QColor('#e7f4ff'),1,Qt.DashLine));p.drawRect(QRectF(self._marquee[0],self._marquee[1]).normalized())
        x = self.gutter+self.cursor*self.pixels_per_second
        p.setPen(QPen(QColor('#f36c85'),2)); p.drawLine(int(x),0,int(x),self.height())

    def mousePressEvent(self, event):
        self.setFocus()
        pos = event.position()
        if pos.y() < self.ruler:
            self.seekRequested.emit(self.time_at(pos.x())); return
        ix = self.hit(pos)
        if ix is None:
            if not event.modifiers() & Qt.ShiftModifier: self.selection.clear()
            self._marquee=(pos,pos)
            self.selectionChanged.emit(sorted(self.selection)); self.update(); return
        if event.button() == Qt.RightButton:
            if self.editor: self.editor.delete(self.track, ix); self.selection.clear(); self.changed.emit()
            return
        if event.modifiers() & Qt.ShiftModifier:
            if ix in self.selection: self.selection.remove(ix)
            else: self.selection.add(ix)
        elif ix not in self.selection: self.selection = {ix}
        if ix in self.selection:
            mode = 'resize' if pos.x() >= self.note_rect(self.notes()[ix]).right()-6 else 'move'
            self._drag = (pos, ix, mode)
        self.selectionChanged.emit(sorted(self.selection)); self.update()

    def mouseMoveEvent(self, event):
        ix = self.hit(event.position())
        if ix is not None:
            n = self.notes()[ix]
            self.setToolTip(f'{pretty_midi.note_number_to_name(n.pitch)} · {n.start:.3f}–{n.end:.3f}s · velocity {n.velocity}')
        if self._marquee:self._marquee=(self._marquee[0],event.position());self.update()
        if self._drag:
            origin,ix,mode=self._drag
            dx=(event.position().x()-origin.x())/self.pixels_per_second
            dy=round((origin.y()-event.position().y())/self.row_height)
            if mode=='move':dx=self.snap(self.notes()[ix].start+dx)-self.notes()[ix].start
            self._preview=(dx,dy);self.update()
            self.setCursor(Qt.SizeHorCursor if mode=='resize' else Qt.ClosedHandCursor)
        else: self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if self._marquee:
            rect=QRectF(self._marquee[0],event.position()).normalized();self._marquee=None
            self.selection.update(ix for ix,n in enumerate(self.notes()) if rect.intersects(self.note_rect(n)))
            self.selectionChanged.emit(sorted(self.selection));self.update();return
        self._preview=None
        if not self._drag or not self.editor: return
        origin, ix, mode = self._drag; self._drag = None; self.unsetCursor()
        dx = (event.position().x()-origin.x())/self.pixels_per_second
        dy = round((origin.y()-event.position().y())/self.row_height)
        if abs(dx)*self.pixels_per_second < 3 and dy == 0: return
        note = self.notes()[ix]
        if mode == 'resize':
            end = max(note.start+.02, self.snap(note.end+dx))
            self.editor.change(self.track, ix, end=end)
        else:
            delta = self.snap(note.start+dx)-note.start
            self.editor.move_notes(self.track, self.selection, delta, dy)
        self.changed.emit()

    def mouseDoubleClickEvent(self, event):
        self._drag = None; self._marquee=None
        if self.editor and event.position().x() >= self.gutter and event.position().y() > self.ruler and self.hit(event.position()) is None:
            ix = self.editor.add(self.track, self.pitch_at(event.position().y()),
                                 self.snap(self.time_at(event.position().x())), self.grid or .25)
            self.selection = {ix}; self.changed.emit(); self.selectionChanged.emit([ix])

    def wheelEvent(self, event):
        if event.modifiers() & Qt.AltModifier and self.editor and self.selection:
            self.editor.transform(self.track,self.selection,velocity_delta=4 if event.angleDelta().y()>0 else -4)
            self.changed.emit(); event.accept()
        elif event.modifiers() & Qt.ControlModifier:
            self.zoom(1.2 if event.angleDelta().y()>0 else 1/1.2); event.accept()
        else: event.ignore()

    def keyPressEvent(self, event):
        if not self.editor: return super().keyPressEvent(event)
        if event.matches(QKeySequence.Cut):
            self.clipboard=self.editor.copy_passage(self.track,sorted(self.selection))
            self.editor.delete_many(self.track,self.selection);self.selection.clear();self.changed.emit();return
        if event.matches(QKeySequence.Copy):
            self.clipboard = self.editor.copy_passage(self.track,sorted(self.selection)); return
        if event.matches(QKeySequence.Paste):
            self.editor.paste_passage(self.track,self.clipboard,self.cursor); self.changed.emit(); return
        if event.matches(QKeySequence.SelectAll):
            self.selection = set(range(len(self.notes()))); self.selectionChanged.emit(sorted(self.selection)); self.update(); return
        if event.matches(QKeySequence.Undo): self.editor.undo(); self.selection.clear(); self.changed.emit(); return
        if event.matches(QKeySequence.Redo): self.editor.redo(); self.selection.clear(); self.changed.emit(); return
        if event.key() in (Qt.Key_Delete,Qt.Key_Backspace):
            self.editor.delete_many(self.track,self.selection); self.selection.clear(); self.changed.emit(); return
        if event.key() in (Qt.Key_Up,Qt.Key_Down,Qt.Key_Left,Qt.Key_Right):
            transpose = (12 if event.modifiers() & Qt.ShiftModifier else 1)*(1 if event.key()==Qt.Key_Up else -1) if event.key() in (Qt.Key_Up,Qt.Key_Down) else 0
            delta = (self.grid or .05)*(1 if event.key()==Qt.Key_Right else -1) if event.key() in (Qt.Key_Left,Qt.Key_Right) else 0
            self.editor.move_notes(self.track,self.selection,delta,transpose); self.changed.emit(); return
        super().keyPressEvent(event)

class Timeline(QWidget):
    seekRequested = Signal(float)
    trackSelected = Signal(int)
    trackShifted = Signal(int,float)
    def __init__(self, parent=None):
        super().__init__(parent); self.pm = None; self.report = {}; self.markers = []
        self.cursor = 0.; self.scale = 35.; self.header = 125; self.row = 64; self.drag = None
        self.setMinimumSize(900,250)
        self.setToolTip('Click ruler to seek. Click track to select. Drag a track lane to shift all its MIDI events.')

    def bind(self, midi, report=None, markers=None):
        self.pm = midi; self.report = report or {}; self.markers = markers or []
        self.setMinimumSize(max(900,int(self.header+(midi.get_end_time()+4)*self.scale)), max(250,45+len(midi.instruments)*self.row))
        self.resize(self.minimumSize()); self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.fillRect(event.rect(), QColor('#111a29'))
        if self.pm is None: return
        first = max(0,int((event.rect().left()-self.header)/self.scale))
        last = int((event.rect().right()-self.header)/self.scale)+1
        for sec in range(first,last+1):
            x = self.header+sec*self.scale; p.setPen(QColor('#31425a')); p.drawLine(int(x),0,int(x),self.height())
            if sec%2==0: p.setPen(QColor('#cad6e8')); p.drawText(int(x)+3,15,f'{sec}s')
        for transition in self.report.get('transitions',[]):
            p.fillRect(QRectF(self.header+transition['start']*self.scale,24,(transition['end']-transition['start'])*self.scale,self.height()-24),QColor(120,85,140,65))
        for index, ins in enumerate(self.pm.instruments):
            y = 42+index*self.row
            p.fillRect(0,y,self.header,self.row-1,QColor('#213148')); p.setPen(QColor(COLORS[index%len(COLORS)]))
            p.drawText(QRectF(4,y+4,self.header-8,self.row-8),Qt.AlignVCenter|Qt.TextWordWrap,ins.name or f'Track {index+1}')
            for n in ins.notes:
                x = self.header+n.start*self.scale
                if x > event.rect().right() or x+(n.end-n.start)*self.scale < event.rect().left(): continue
                p.fillRect(QRectF(x,y+8+(100-max(24,min(100,n.pitch)))*.5,max(2,(n.end-n.start)*self.scale),3),QColor(COLORS[index%len(COLORS)]))
        for marker in self.markers:
            x = self.header+float(marker['time'])*self.scale
            p.setPen(QColor('#ecd083')); p.drawLine(int(x),20,int(x),self.height()); p.drawText(int(x)+3,34,str(marker['label']))
        x = self.header+self.cursor*self.scale; p.setPen(QPen(QColor('#f36c85'),2)); p.drawLine(int(x),0,int(x),self.height())

    def mousePressEvent(self,event):
        pos = event.position()
        if pos.y()<42:
            self.seekRequested.emit(max(0,(pos.x()-self.header)/self.scale)); return
        ix = int((pos.y()-42)//self.row)
        if self.pm is not None and 0 <= ix < len(self.pm.instruments):
            self.trackSelected.emit(ix); self.drag = (ix,pos.x())

    def mouseReleaseEvent(self,event):
        if self.drag:
            ix, origin = self.drag; self.drag = None
            dx = event.position().x()-origin
            if abs(dx)>4: self.trackShifted.emit(ix,dx/self.scale)

class Waveform(QWidget):
    def __init__(self): super().__init__(); self.data = None; self.setMinimumHeight(100)
    def paintEvent(self,event):
        p = QPainter(self); p.fillRect(self.rect(),QColor('#142134'))
        if not self.data: return
        peaks = self.data['peaks']; p.setPen(QColor('#65c7b4'))
        for ix, peak in enumerate(peaks):
            x = int(ix*self.width()/max(1,len(peaks))); size = min(1,peak)*self.height()*.42
            p.drawLine(x,int(self.height()/2-size),x,int(self.height()/2+size))
        p.setPen(QColor('#e1e9f0')); p.drawText(8,18,f"Decoded waveform · {self.data['duration']:.2f}s")


class AutomationCurve(QWidget):
    """Click to add, drag to move, right-click to remove linear gain points."""
    changed=Signal(object)
    def __init__(self,points=None,duration=10,parent=None):
        super().__init__(parent);self.points=[list(p) for p in (points or [])]
        self.duration=max(1,float(duration));self.drag=None;self.margin=24
        self.setMinimumSize(560,260);self.setMouseTracking(True)
        self.setToolTip('Click: add point · Drag: move point · Right-click: delete · gain range 0–2')

    def point_position(self,point):
        from PySide6.QtCore import QPointF
        return QPointF(self.margin+point[0]/self.duration*(self.width()-2*self.margin),self.height()-self.margin-point[1]/2*(self.height()-2*self.margin))

    def value_at(self,pos):
        time=max(0,min(self.duration,(pos.x()-self.margin)/(self.width()-2*self.margin)*self.duration))
        gain=max(0,min(2,(self.height()-self.margin-pos.y())/(self.height()-2*self.margin)*2))
        return [round(time,3),round(gain,3)]

    def hit(self,pos):
        return next((ix for ix,p in enumerate(self.points) if (self.point_position(p)-pos).manhattanLength()<12),None)

    def paintEvent(self,event):
        from PySide6.QtCore import QPointF
        p=QPainter(self);p.fillRect(self.rect(),QColor('#142134'))
        for gain in (0,1,2):
            y=self.point_position([0,gain]).y();p.setPen(QColor('#40516a'));p.drawLine(self.margin,int(y),self.width()-self.margin,int(y))
            p.setPen(QColor('#cad8e5'));p.drawText(2,int(y)+4,str(gain))
        p.drawText(self.margin,self.height()-4,'0s');p.drawText(self.width()-70,self.height()-4,f'{self.duration:.1f}s')
        points=sorted(self.points)
        if points:
            p.setPen(QPen(QColor('#77d5ba'),2));previous=self.point_position([0,points[0][1]])
            for point in points:
                pos=self.point_position(point);p.drawLine(previous,pos);p.drawEllipse(pos,4,4);previous=pos
            p.drawLine(previous,self.point_position([self.duration,points[-1][1]]))

    def mousePressEvent(self,event):
        ix=self.hit(event.position())
        if event.button()==Qt.RightButton:
            if ix is not None:self.points.pop(ix);self.changed.emit(sorted(self.points));self.update()
            return
        if ix is None:
            value=self.value_at(event.position())
            # Duplicate times replace the gain rather than creating invalid points.
            ix=next((i for i,p in enumerate(self.points) if p[0]==value[0]),None)
            if ix is None:self.points.append(value);ix=len(self.points)-1
            else:self.points[ix]=value
        self.drag=ix;self.update()

    def mouseMoveEvent(self,event):
        if self.drag is not None:
            value=self.value_at(event.position())
            if not any(i!=self.drag and p[0]==value[0] for i,p in enumerate(self.points)):
                self.points[self.drag]=value;self.update()

    def mouseReleaseEvent(self,event):
        self.drag=None;self.points.sort();self.changed.emit(self.points);self.update()
