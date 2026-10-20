import json, os, sys, traceback, webbrowser, tempfile
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QUrl
from PySide6.QtGui import QColor,QPainter,QPen,QBrush
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
 QPushButton,QListWidget,QListWidgetItem,QFileDialog,QComboBox,QSpinBox,QDoubleSpinBox,QSlider,QTextEdit,QProgressBar,
 QMessageBox,QSplitter,QGroupBox,QCheckBox,QTabWidget,QScrollArea,QToolBar,QInputDialog)
from .engine import Settings,analyse,arrange,load,inspect_audio,render_audio,export_musicxml
from .editing import MidiEditor
from .preview import render_preview
from .imports import metadata,acquire,extract_local_audio,transcribe_audio,AUDIO,MIDI

class Worker(QThread):
    done=Signal(object);failed=Signal(str)
    def __init__(self,fn,*args):super().__init__();self.fn=fn;self.args=args
    def run(self):
        try:self.done.emit(self.fn(*self.args))
        except Exception:self.failed.emit(traceback.format_exc())

from .widgets import PianoRoll

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('TR1PP Mashup Studio 2.0 — Development');self.resize(1300,850)
        self.paths=[];self.pm=None;self.editor=None;self.player=None;self.report={};self.output=None;self.worker=None;self.jobs=[]
        self.setStyleSheet('QWidget{background:#111827;color:#ebf2fb;font-size:12px} QGroupBox{border:1px solid #344258;border-radius:7px;margin-top:10px;padding:11px} QGroupBox::title{color:#92cef8} QPushButton{background:#263b55;border:1px solid #405d80;border-radius:5px;padding:8px} QPushButton:hover{background:#3b5b7e} QTextEdit,QListWidget,QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{background:#192638;border:1px solid #324459;border-radius:4px;padding:5px} QProgressBar{background:#25344b;border:none;border-radius:4px} QProgressBar::chunk{background:#57c8af}')
        central=QWidget();self.setCentralWidget(central);outer=QVBoxLayout(central)
        head=QHBoxLayout();head.addWidget(QLabel('TR1PP MASHUP STUDIO  /  SOURCE-AWARE ARRANGER'))
        search=QLineEdit();search.setPlaceholderText('Paste YouTube/Vimeo HTTPS URL or type a title to search');self.search=search;head.addWidget(search,1)
        b=QPushButton('Search versions');b.clicked.connect(self.search_song);head.addWidget(b)
        b=QPushButton('Inspect URL');b.clicked.connect(self.inspect_url);head.addWidget(b)
        b=QPushButton('Import URL audio');b.clicked.connect(self.import_url);head.addWidget(b);outer.addLayout(head)
        splitter=QSplitter(Qt.Horizontal);outer.addWidget(splitter,1)
        left=QWidget();left.setMinimumWidth(350);left.setMaximumWidth(480);lv=QVBoxLayout(left);splitter.addWidget(left)
        grp=QGroupBox('Ordered source collection');vv=QVBoxLayout(grp);self.items=QListWidget();self.items.setDragDropMode(QListWidget.InternalMove);vv.addWidget(self.items)
        controls=QHBoxLayout()
        for label,fn in [('Add MIDI/audio/video',self.add_files),('Remove',self.remove_file),('Up',lambda:self.move(-1)),('Down',lambda:self.move(1))]:
            q=QPushButton(label);q.clicked.connect(fn);controls.addWidget(q)
        vv.addLayout(controls)
        actions=QHBoxLayout()
        for label,fn in [('Transcribe selected audio',self.transcribe_selected),('Preview selected',self.preview_selected)]:
            bb=QPushButton(label);bb.clicked.connect(fn);actions.addWidget(bb)
        vv.addLayout(actions);lv.addWidget(grp)
        cfg=QGroupBox('Arrangement engine');form=QFormLayout(cfg)
        self.style=QComboBox();self.style.addItems(['Seamless Transition','Full Mashup','Classical','Jazz Fusion','Virtuoso Piano','Cinematic','Ragtime','Custom']);form.addRow('Style target',self.style)
        self.bridge=QSpinBox();self.bridge.setRange(2,32);self.bridge.setValue(8);form.addRow('Bridge length / bars',self.bridge)
        self.cross=QSpinBox();self.cross.setRange(0,16);self.cross.setValue(4);form.addRow('Overlap target (planned)',self.cross)
        self.bpm=QDoubleSpinBox();self.bpm.setRange(0,300);self.bpm.setSpecialValueText('Auto');form.addRow('Bridge BPM',self.bpm)
        self.difficulty=QSlider(Qt.Horizontal);self.difficulty.setRange(0,100);self.difficulty.setValue(65);form.addRow('Structure plan difficulty',self.difficulty)
        self.human=QSpinBox();self.human.setRange(0,35);self.human.setValue(7);form.addRow('Humanize ±ms',self.human)
        self.strict=QCheckBox('Filter extreme simultaneous hand spans');self.strict.setChecked(True);form.addRow(self.strict)
        lv.addWidget(cfg)
        buttons=QHBoxLayout()
        for name,fn in [('Analyze',self.analyze),('Generate arrangement',self.generate)]:
            b=QPushButton(name);b.clicked.connect(fn);buttons.addWidget(b)
        lv.addLayout(buttons)
        exp=QHBoxLayout()
        for name,fn in [('Export MIDI',self.export_midi),('Export report',self.export_report),('Save project',self.save_project),('Open project',self.open_project)]:
            b=QPushButton(name);b.clicked.connect(fn);exp.addWidget(b)
        lv.addLayout(exp)
        exp2=QHBoxLayout()
        for name,fn in [('Render WAV / FLAC / MP3',self.export_audio),('MusicXML',self.export_score),('Open source',self.open_source),('Build EXE instructions',self.show_exe_help)]:
            b=QPushButton(name);b.clicked.connect(fn);exp2.addWidget(b)
        lv.addLayout(exp2)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);lv.addWidget(self.progress)
        right=QWidget();rv=QVBoxLayout(right);splitter.addWidget(right)
        tabs=QTabWidget();self.tabs=tabs;rv.addWidget(tabs)
        ptab=QWidget();pbox=QVBoxLayout(ptab);self.roll=PianoRoll();self.roll_scroll=QScrollArea();self.roll_scroll.setWidget(self.roll);pbox.addWidget(self.roll_scroll);pbox.addWidget(QLabel('Double-click: add · Drag: move/resize · Shift-click: select · Ctrl+C/V · Delete · Ctrl+wheel: zoom · Alt+wheel: velocity'))
        editor_controls=QHBoxLayout()
        for title,handler in [('Add note',self.edit_add),('Edit note',self.edit_change),('Delete note',self.edit_delete),('Undo',self.edit_undo),('Redo',self.edit_redo),('Play preview',self.play_preview),('Stop',self.stop_preview)]:
            b=QPushButton(title);b.clicked.connect(handler);editor_controls.addWidget(b)
        pbox.addLayout(editor_controls);tabs.addTab(ptab,'Piano roll')
        logtab=QWidget();vb=QVBoxLayout(logtab);self.text=QTextEdit();self.text.setReadOnly(True);vb.addWidget(self.text);tabs.addTab(logtab,'Analysis / quality')
        self.log('Paste a supported video URL and click Inspect URL, then Import URL audio for media you are authorised to download. Audio-to-MIDI requires the optional Basic Pitch model; original MIDIs give much better accuracy.')
    def log(self,msg):self.text.append(str(msg))
    def paths_now(self):return [self.items.item(i).data(Qt.UserRole) for i in range(self.items.count())]
    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Choose source files','','Music (*.mid *.midi *.wav *.mp3 *.flac *.ogg *.m4a *.mp4 *.webm *.aac *.aif *.aiff *.wma *.mov *.mkv *.avi *.m4v *.opus)')
        for file in files:self.add_item(file)
    def add_item(self,path):
        if not Path(path).is_file():
            self.log('File missing: '+str(path));return
        it=QListWidgetItem(Path(path).name);it.setData(Qt.UserRole,str(path));self.items.addItem(it)
    def remove_file(self):
        for it in self.items.selectedItems():self.items.takeItem(self.items.row(it))
    def move(self,d):
        i=self.items.currentRow();j=i+d
        if 0<=i<self.items.count() and 0<=j<self.items.count():it=self.items.takeItem(i);self.items.insertItem(j,it);self.items.setCurrentRow(j)
    def settings(self):return Settings(mode=self.style.currentText(),bridge_bars=self.bridge.value(),crossfade_bars=self.cross.value(),target_bpm=self.bpm.value(),difficulty=self.difficulty.value(),humanize_ms=self.human.value(),strict_two_hands=self.strict.isChecked())
    def work(self,fn,*args,callback):
        self.progress.setRange(0,0);self.worker=Worker(fn,*args)
        def success(res):self.progress.setRange(0,100);self.progress.setValue(100);callback(res)
        def failure(err):self.progress.setRange(0,100);self.progress.setValue(0);self.log(err);QMessageBox.critical(self,'Processing failed',err.splitlines()[-1] if err.splitlines() else err)
        self.worker.done.connect(success);self.worker.failed.connect(failure);self.worker.start()
    def analyze(self):
        paths=self.paths_now()
        def task():
            results=[]
            for f in paths:
                try:results.append({'file':f,'analysis':analyse(load(f)) if Path(f).suffix.lower() in ('.mid','.midi') else inspect_audio(f)})
                except Exception as e:results.append({'file':f,'error':str(e)})
            return results
        self.work(task,callback=lambda x:self.log(json.dumps(x,indent=2)))
    def generate(self):
        files=self.paths_now()
        if len(files)<2:QMessageBox.warning(self,'Sources required','Import two or more MIDI files.');return
        if any(Path(f).suffix.lower() not in ('.mid','.midi') for f in files):QMessageBox.warning(self,'Transcription required','Select each audio source and click Transcribe selected audio first, or import accurate source MIDI files.');return
        self.work(arrange,files,self.settings(),callback=self.generated)
    def generated(self,result):
        self.pm,self.report=result;self.editor=MidiEditor(self.pm);self.roll.set_midi(self.pm)
        self.log('ARRANGEMENT GENERATED\n'+json.dumps(self.report,indent=2))
    def export_midi(self):
        if self.pm is None:return self.no_output()
        path,_=QFileDialog.getSaveFileName(self,'Export MIDI','TR1PP Mashup.mid','MIDI (*.mid)')
        if path:self.pm.write(path);self.log('Saved '+path)
    def export_report(self):
        if not self.report:return self.no_output()
        path,_=QFileDialog.getSaveFileName(self,'Save analysis','quality-report.json','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(self.report,indent=2),encoding='utf-8')
    def export_audio(self):
        if self.pm is None:return self.no_output()
        sf,_=QFileDialog.getOpenFileName(self,'Select downloaded SF2 SoundFont','','SoundFont (*.sf2)')
        if not sf:return
        path,_=QFileDialog.getSaveFileName(self,'Rendered audio','TR1PP Mashup.wav','WAV (*.wav);;FLAC (*.flac);;MP3 (*.mp3)')
        if path:self.work(render_audio,self.pm,path,sf,callback=lambda x:self.log('Rendered '+str(x)))
    def export_score(self):
        if self.pm is None:return self.no_output()
        path,_=QFileDialog.getSaveFileName(self,'Export MusicXML','TR1PP Mashup.musicxml','MusicXML (*.musicxml)')
        if path:self.work(export_musicxml,self.pm,path,callback=lambda x:self.log('Saved score '+str(x)))
    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'Save editable project','TR1PP project.tr1pp.json','Project (*.json)')
        if path:
            obj={'format':'tr1pp-project-v1','sources':self.paths_now(),'settings':vars(self.settings()),'export_midi':None}
            if self.pm:
                mid_path=str(Path(path).with_suffix('.mid'));self.pm.write(mid_path);obj['export_midi']=mid_path
            Path(path).write_text(json.dumps(obj,indent=2),encoding='utf-8');self.log('Saved project '+path)
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open project','','Project (*.json)')
        if not path:return
        obj=json.loads(Path(path).read_text(encoding='utf-8'));self.items.clear()
        for f in obj['sources']:self.add_item(f)
        s=obj.get('settings',{});self.style.setCurrentText(s.get('mode','Seamless Transition'));self.bridge.setValue(s.get('bridge_bars',8));self.cross.setValue(s.get('crossfade_bars',4));self.bpm.setValue(s.get('target_bpm',0));self.human.setValue(int(s.get('humanize_ms',7)));self.strict.setChecked(s.get('strict_two_hands',True))
        if obj.get('export_midi') and Path(obj['export_midi']).exists():self.pm=load(obj['export_midi']);self.editor=MidiEditor(self.pm);self.roll.set_midi(self.pm)
        self.log('Project loaded. Original source files must remain at recorded locations.')
    def open_source(self):
        f=self.items.currentItem()
        if f:os.startfile(f.data(Qt.UserRole)) if sys.platform=='win32' else webbrowser.open(Path(f.data(Qt.UserRole)).as_uri())
    def inspect_url(self):
        url=self.search.text().strip()
        if not url.startswith('https://'):
            QMessageBox.information(self,'Paste a URL','Paste a direct HTTPS video URL first.');return
        self.work(metadata,url,callback=lambda x:self.log('VIDEO METADATA\n'+json.dumps(x,indent=2)))
    def import_url(self):
        url=self.search.text().strip()
        if not url.startswith('https://'):
            QMessageBox.information(self,'Paste a URL','Paste a direct HTTPS video URL first.');return
        choice=QMessageBox.question(self,'Import authorised audio','Only import audio that you own or are authorised to download. Continue?')
        if choice!=QMessageBox.Yes:return
        folder=Path.home()/'Documents'/'TR1PP Mashup Studio'/'Imported Audio'
        def finished(path):
            self.add_item(path)
            self.log('Imported audio: '+path+'\nSelect it and click Transcribe selected audio to create an approximate MIDI.')
        self.work(acquire,url,str(folder),callback=finished)
    def transcribe_selected(self):
        it=self.items.currentItem()
        if not it:return QMessageBox.information(self,'Select audio','Select an audio file first.')
        path=it.data(Qt.UserRole)
        if Path(path).suffix.lower() in MIDI:return QMessageBox.information(self,'Already MIDI','This source is already a MIDI file.')
        folder=Path.home()/'Documents'/'TR1PP Mashup Studio'/'Transcriptions'
        def task():
            wav=extract_local_audio(path,str(folder))
            return transcribe_audio(wav,str(folder))
        def finished(info):
            row=self.items.row(it)
            self.add_item(info['midi_path'])
            replacement=self.items.takeItem(self.items.count()-1)
            self.items.insertItem(row+1,replacement)
            self.log('Transcribed: '+info['midi_path']+'\n'+info['message']+'\nRemove the audio source from the list before Generate.')
        self.work(task,callback=finished)
    def preview_selected(self):
        it=self.items.currentItem()
        if not it:return
        path=it.data(Qt.UserRole)
        if Path(path).suffix.lower() in MIDI:
            self.work(load,path,callback=lambda pm:(self.roll.set_midi(pm),self.log('MIDI preview on piano roll: '+path)))
        else:self.open_source()
    def _edit_ready(self):
        if self.pm is None:
            self.no_output();return False
        if self.editor is None:self.editor=MidiEditor(self.pm)
        return True
    def _choose_note(self):
        if not self._edit_ready():return None
        track,ok=QInputDialog.getInt(self,'Track','Track index (0 = left, 1 = right)',1,0,len(self.pm.instruments)-1)
        if not ok:return None
        notes=self.pm.instruments[track].notes
        if not notes:
            QMessageBox.information(self,'Empty track','Add a note first.');return None
        index,ok=QInputDialog.getInt(self,'Note index','Note index (0-based)',0,0,len(notes)-1)
        return (track,index) if ok else None
    def _edited(self):
        self.pm=self.editor.pm;self.roll.set_midi(self.pm)
        self.log('MIDI edit applied. Export or save to persist.')
    def edit_add(self):
        if not self._edit_ready():return
        track,ok=QInputDialog.getInt(self,'Add note','Track (0 left / 1 right)',1,0,len(self.pm.instruments)-1)
        if not ok:return
        pitch,ok=QInputDialog.getInt(self,'Add note','MIDI pitch (0–127)',64,0,127)
        if not ok:return
        start,ok=QInputDialog.getDouble(self,'Add note','Start (seconds)',0,0,100000,3)
        if not ok:return
        length,ok=QInputDialog.getDouble(self,'Add note','Duration (seconds)',.25,.01,300,3)
        if not ok:return
        self.editor.add(track,pitch,start,length);self._edited()
    def edit_change(self):
        sel=self._choose_note()
        if sel is None:return
        track,index=sel;n=self.pm.instruments[track].notes[index]
        pitch,ok=QInputDialog.getInt(self,'Edit note','MIDI pitch',n.pitch,0,127)
        if not ok:return
        start,ok=QInputDialog.getDouble(self,'Edit note','Start (seconds)',n.start,0,100000,3)
        if not ok:return
        duration,ok=QInputDialog.getDouble(self,'Edit note','Duration (seconds)',n.end-n.start,.01,300,3)
        if not ok:return
        velocity,ok=QInputDialog.getInt(self,'Edit note','Velocity',n.velocity,1,127)
        if not ok:return
        self.editor.change(track,index,pitch=pitch,start=start,end=start+duration,velocity=velocity);self._edited()
    def edit_delete(self):
        sel=self._choose_note()
        if sel is not None:self.editor.delete(*sel);self._edited()
    def edit_undo(self):
        if self._edit_ready() and self.editor.undo():self._edited()
    def edit_redo(self):
        if self._edit_ready() and self.editor.redo():self._edited()
    def play_preview(self):
        if not self._edit_ready():return
        def finished(path):
            try:
                from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
                if self.player is None:
                    self.player=QMediaPlayer(self);self.audio_output=QAudioOutput(self)
                    self.player.setAudioOutput(self.audio_output)
                    self.audio_output.setVolume(.6)
                self.player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
                self.player.play();self.log('Playing synthetic preview. Audio output depends on Qt Multimedia backend.')
            except Exception as e:self.log('Audio playback unavailable: '+str(e))
        self.work(render_preview,self.pm,str(Path(tempfile.gettempdir())/'tr1pp_preview.wav'),callback=finished)
    def stop_preview(self):
        if self.player is not None:self.player.stop()
    def search_song(self):
        term=self.search.text().strip()
        if term and term.startswith('https://'):return self.inspect_url()
        if term:webbrowser.open('https://www.youtube.com/results?search_query='+__import__('urllib.parse',fromlist=['quote']).quote(term))
    def show_exe_help(self):QMessageBox.information(self,'Build executable','Run build_exe.bat on Windows after setup.bat. PyInstaller produces dist\\TR1PP Mashup Studio\\. See README.')
    def no_output(self):QMessageBox.information(self,'Nothing to export','Generate an arrangement first.')

def run():
    from .studio import run as studio_run
    studio_run()
