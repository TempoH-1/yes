"""Integrated studio shell built on the retained source-arrangement interface."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSettings, QStandardPaths, QUrl, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication,QToolBar,QComboBox,QPushButton,QLabel,QSpinBox,
 QDoubleSpinBox,QSlider,QCheckBox,QFileDialog,QMessageBox,QInputDialog,QScrollArea,
 QWidget,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,QAbstractItemView,QProgressDialog,QDialog,QDialogButtonBox,QFormLayout)
from .gui import Window, Worker
from .editing import MidiEditor
from .engine import load, analyse, Settings
from .project import Project, TrackMix, save_project, load_project, materialize_sources, snapshot
from .audio import render_mix, export_stems, waveform
from .transcription import TranscriptionOptions, transcribe, decode_audio, model_status
from .widgets import Timeline, Waveform, AutomationCurve
from .planning import ArrangementPlan,preset_plan,render_plan,harmonic_timeline
from .imports import acquire, AUDIO, MIDI

class StudioWindow(Window):
    workflowProgress=Signal(int,str)
    def __init__(self):
        self.project = Project(); self.source_origins={}; self.project_path = None; self.revision = 0; self.dirty = False
        self._building = True; self._closing = False; self.render_path = None; self.render_revision = -1
        default = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        self.data_dir = Path(os.environ.get('TR1PP_DATA_DIR',default))
        self.data_dir.mkdir(parents=True,exist_ok=True)
        self.preferences=QSettings(str(self.data_dir/'settings.ini'),QSettings.IniFormat)
        self.workflow_dialog=None
        self.soundfont = str(self.preferences.value('soundfont',''))
        if self.soundfont and not Path(self.soundfont).is_file(): self.soundfont = ''
        if not self.soundfont:
            for candidate in ['/usr/share/sounds/sf2/default-GM.sf2','/usr/share/sounds/sf2/TimGM6mb.sf2']:
                if Path(candidate).is_file():self.soundfont=candidate;break
        super().__init__()
        self.workflowProgress.connect(self.workflow_progress)
        self.roll.changed.connect(self._edited)
        self.roll.seekRequested.connect(self.seek)
        self.roll.selectionChanged.connect(self.selection_changed)
        self.items.itemDoubleClicked.connect(lambda *_:self.edit_source())
        self.items.model().rowsMoved.connect(lambda *_:self.mark_dirty())
        self._build_edit_toolbar(); self._build_timeline(); self._build_mixer(); self._build_transport(); self._build_planning()
        self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(60000)
        self.autosave_timer.timeout.connect(self.autosave); self.autosave_timer.start()
        self._building = False
        self.statusBar().showMessage('Development checkpoint · Source-derived arrangement · Synthetic preview unless SF2 selected')
        self.log('2.0 development: double-click a MIDI source to edit it. Projects embed source files and MIDI. Recovery snapshots are saved every 60 seconds after changes.')
        self.log('Transcription setup: python tools/install_transcription.py. Model activations are not calibrated confidence scores.')
        self.bind_editor(MidiEditor(self.project.midi))

    def _button(self,bar,label,fn):
        button = QPushButton(label); button.clicked.connect(fn); bar.addWidget(button); return button

    def _build_edit_toolbar(self):
        bar = QToolBar('Editing',self); self.addToolBar(Qt.TopToolBarArea,bar)
        bar.addWidget(QLabel('Edit track ')); self.track_select = QComboBox(); self.track_select.setMinimumWidth(135)
        self.track_select.currentIndexChanged.connect(self.select_track); bar.addWidget(self.track_select)
        self._button(bar,'Open source in editor',self.edit_source)
        self._button(bar,'New track',self.new_track)
        self._button(bar,'Split hands',self.split_hands)
        bar.addWidget(QLabel(' Grid ')); self.grid_select = QComboBox()
        self.grid_select.addItems(['1/4 beat','1/2 beat','1 beat','Off']); self.grid_select.setCurrentIndex(1)
        self.grid_select.currentIndexChanged.connect(self.update_grid); bar.addWidget(self.grid_select)
        self._button(bar,'Quantise',self.quantise_selection)
        self._button(bar,'Humanise',self.humanise_selection)
        self._button(bar,'−',lambda:self.roll.zoom(1/1.25)); self._button(bar,'+',lambda:self.roll.zoom(1.25))
        bar2 = QToolBar('Note properties',self); self.addToolBarBreak(); self.addToolBar(bar2)
        self.velocity = QSpinBox(); self.velocity.setRange(1,127); self.velocity.setValue(80)
        bar2.addWidget(QLabel('Selection velocity ')); bar2.addWidget(self.velocity)
        self._button(bar2,'Apply velocity',self.set_selection_velocity)
        self._button(bar2,'Transpose',self.transpose_selection)
        self._button(bar2,'Sustain',self.add_sustain)
        self._button(bar2,'Tempo',self.change_tempo)
        self._button(bar2,'Add marker',self.add_marker)
        self._button(bar2,'SoundFont',self.choose_soundfont)
        self._button(bar2,'Export stems',self.export_stem_files)
        self._button(bar2,'Snapshot',self.manual_snapshot)
        self._button(bar2,'Recover',self.recover_project)
        self._button(bar2,'Batch URLs',self.batch_urls)
        self._button(bar2,'Transcription settings',self.configure_transcription)
        self._button(bar2,'Source waveform',self.inspect_waveform)
        self.transcription_options = TranscriptionOptions()
        for text,shortcut,fn in [('Save',QKeySequence.Save,self.save_project),('Open',QKeySequence.Open,self.open_project)]:
            action=QAction(text,self);action.setShortcut(shortcut);action.triggered.connect(fn);self.addAction(action)

    def _build_timeline(self):
        self.timeline = Timeline(); scroll = QScrollArea(); scroll.setWidget(self.timeline)
        self.tabs.addTab(scroll,'Multitrack timeline')
        self.timeline.seekRequested.connect(self.seek)
        self.timeline.trackSelected.connect(lambda ix:self.track_select.setCurrentIndex(ix))
        self.timeline.trackShifted.connect(self.shift_track)
        self.wave = Waveform(); self.tabs.addTab(self.wave,'Source waveform')

    def _build_mixer(self):
        self.mixer_table = QTableWidget(0,7)
        self.mixer_table.setHorizontalHeaderLabels(['Track','Volume','Pan','Mute','Solo','Gain automation','Effects'])
        self.mixer_table.horizontalHeader().setStretchLastSection(True)
        self.mixer_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.mixer_table,'Mixer / automation')

    def _build_transport(self):
        bar = QToolBar('Transport',self); self.addToolBar(Qt.BottomToolBarArea,bar)
        self._button(bar,'Play / pause',self.toggle_playback); self._button(bar,'Stop',self.stop_preview)
        self.position = QSlider(Qt.Horizontal); self.position.setRange(0,0); self.position.setMinimumWidth(180)
        self.position.sliderMoved.connect(lambda ms:self.seek(ms/1000)); bar.addWidget(self.position)
        self.time_label = QLabel('0.00 / 0.00 s'); bar.addWidget(self.time_label)
        self.loop = QCheckBox('Loop'); bar.addWidget(self.loop)
        self.loop_start = QDoubleSpinBox(); self.loop_end = QDoubleSpinBox()
        for label, box in [('From',self.loop_start),('To',self.loop_end)]:
            box.setRange(0,36000); box.setDecimals(2); bar.addWidget(QLabel(label)); bar.addWidget(box)
        bar.addWidget(QLabel('Output ')); self.devices=QComboBox(); bar.addWidget(self.devices)
        self.devices.currentIndexChanged.connect(self.device_changed)
        try:
            from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput,QMediaDevices
            self.player=QMediaPlayer(self); self.audio_output=QAudioOutput(self)
            self.audio_output.setVolume(.8); self.player.setAudioOutput(self.audio_output)
            self.player.positionChanged.connect(self.playback_position)
            self.player.durationChanged.connect(lambda ms:self.position.setRange(0,ms))
            self.player.errorOccurred.connect(lambda *_:self.log('Playback: '+self.player.errorString()))
            self.player.mediaStatusChanged.connect(self.media_status)
            self.devices.addItem('System default',None)
            for device in QMediaDevices.audioOutputs():self.devices.addItem(device.description(),device)
        except (ImportError,RuntimeError) as e:self.log('Qt playback unavailable: '+str(e)); self.player=None

    def _build_planning(self):
        self.custom_plan=None;self.transition_candidates=[];self.audition=False
        bar=QToolBar('Structure and transition planning',self);self.addToolBarBreak();self.addToolBar(bar)
        bar.addWidget(QLabel('Structure '));self.structure=QComboBox()
        self.structure.addItems(['Complete sources + bridges','A/B/A thematic','Layered motifs','Call and response','Custom plan'])
        bar.addWidget(self.structure)
        self._button(bar,'Import → analyse → compose',self.automatic_workflow)
        self._button(bar,'Edit structure plan',self.edit_structure_plan)
        self._button(bar,'Harmonic analysis',self.show_harmony)
        bar.addWidget(QLabel(' Transition '));self.transition_select=QComboBox();bar.addWidget(self.transition_select)
        self._button(bar,'Compare bridges',self.compare_transitions)
        self.candidate_select=QComboBox();bar.addWidget(self.candidate_select)
        self.transition_select.currentIndexChanged.connect(self.clear_candidates)
        self._button(bar,'Audition candidate',self.audition_candidate)
        self._button(bar,'Apply candidate',self.apply_candidate)

    def generate(self):
        files=self.paths_now()
        if len(files)<2:return self.log('Import at least two MIDI sources before generating.')
        if any(Path(p).suffix.lower() not in MIDI for p in files):
            return self.log('Transcribe audio/video sources first; the transcription replaces its source with editable MIDI.')
        mode=self.structure.currentText()
        if self.dirty and self.pm is not None and self.pm.instruments:
            if self.manual_snapshot() is None:return
        if mode=='Complete sources + bridges':return super().generate()
        if mode=='Custom plan':
            if self.custom_plan is None:return self.log('Use Edit structure plan to create a custom plan first.')
            return self.work(render_plan,files,self.custom_plan,callback=self.generated)
        bpm=self.bpm.value() or 120;difficulty=self.difficulty.value()
        def task():
            plan=preset_plan(files,mode,bpm,difficulty)
            return render_plan(files,plan)
        self.work(task,callback=self.generated)

    def automatic_workflow(self):
        import threading
        from .workflow import prepare_project
        sources=self.paths_now()
        if not sources:return self.log('Add source recordings or MIDI files first.')
        if self.structure.currentText()=='Custom plan':return self.log('Run automatic import with a preset first, then edit the structure plan.')
        if self.dirty and self.pm is not None and self.pm.instruments and self.manual_snapshot() is None:return
        def ready(project):
            self.project=project;self.source_origins={};self.items.clear();self._building=True
            try:
                for source in project.sources:self.add_item(source)
            finally:self._building=False
            self.generated((project.midi,project.report))
            for error in project.report['import_workflow']['errors']:self.log('Source failed: '+error['source']+' · '+error['error'])
        self.workflow_cancel=threading.Event()
        self.workflow_dialog=QProgressDialog('Preparing sources…','Cancel after current source operation',0,100,self)
        self.workflow_dialog.setWindowTitle('Import → analyse → compose');self.workflow_dialog.setAutoClose(False)
        self.workflow_dialog.canceled.connect(self.workflow_cancel.set);self.workflow_dialog.show()
        started=self.work(prepare_project,sources,self.data_dir/'workflow',self.settings(),self.structure.currentText(),self.transcription_options,self.workflowProgress.emit,self.workflow_cancel,callback=ready)
        if not started:self.workflow_dialog.close();self.workflow_dialog=None

    def workflow_progress(self,percent,message):
        if self.workflow_dialog is not None:
            self.workflow_dialog.setValue(percent);self.workflow_dialog.setLabelText(message)
        self.statusBar().showMessage(message)

    def selection_changed(self,indices):
        notes=self.roll.notes()
        if indices and indices[0]<len(notes):self.velocity.setValue(notes[indices[0]].velocity)
        self.statusBar().showMessage(f'{len(indices)} selected notes · Track {self.roll.track+1}')

    def clear_candidates(self,*_):
        self.transition_candidates=[]
        if hasattr(self,'candidate_select'):self.candidate_select.clear()

    def edit_structure_plan(self):
        files=self.paths_now()
        if len(files)<2 or any(Path(p).suffix.lower() not in MIDI for p in files):return self.log('Import/transcribe at least two MIDI sources first.')
        def edit(plan):
            from dataclasses import asdict
            text,ok=QInputDialog.getMultiLineText(self,'Arrangement structure','Source indices are 0-based; source times in seconds, placement in beats. Edit excerpts, repeats, gain and transposition.',json.dumps(asdict(plan),indent=2))
            if not ok:return
            try:
                candidate=ArrangementPlan.from_dict(json.loads(text));candidate.validate(len(files))
                self.custom_plan=candidate;self.project.settings['custom_plan']=json.loads(text);self.structure.setCurrentText('Custom plan');self.mark_dirty()
            except (ValueError,TypeError) as e:QMessageBox.warning(self,'Invalid plan',str(e))
        if self.custom_plan is not None:edit(self.custom_plan)
        else:self.work(preset_plan,files,'A/B/A thematic',self.bpm.value() or 120,self.difficulty.value(),callback=edit)

    def show_harmony(self):
        if self.pm is None or not self.pm.instruments:return
        self.work(harmonic_timeline,copy.deepcopy(self.pm),callback=lambda rows:self.log('Bar-level triad estimates (coverage is a heuristic, not calibrated confidence)\n'+json.dumps(rows,indent=2)))

    def compare_transitions(self):
        transitions=self.report.get('transitions',[]);index=self.transition_select.currentIndex();files=self.paths_now()
        if not 0<=index<len(transitions):return self.log('Generate a complete-source arrangement to compare its bridge candidates.')
        record=transitions[index];source_index=record['after_song'];settings=self.report.get('settings',{})
        def task():
            from .engine import _make_bridge,key_estimate
            import pretty_midi
            if source_index>=len(files):raise ValueError('Original source collection changed; regenerate the arrangement first.')
            signatures=self.report.get('source_signatures')
            if signatures and signatures!=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files]:raise ValueError('Source collection changed; regenerate before comparing transitions.')
            a,b=load(files[source_index-1]),load(files[source_index])
            root_a=key_estimate(a)[1];root_b=key_estimate(b)[1]
            bpm=settings.get('target_bpm') or (analyse(a)['bpm_estimate']+analyse(b)['bpm_estimate'])/2
            duration=record['end']-record['start'];candidates=[]
            for variant in range(3):
                ins,score=_make_bridge(a,b,0,duration,max(45,min(240,bpm)),root_a,root_b,settings.get('mode','Seamless Transition'),variant)
                midi=pretty_midi.PrettyMIDI(initial_tempo=bpm);midi.instruments=[ins];candidates.append((midi,score))
            return candidates
        def compared(candidates):
            self.transition_candidates=candidates;self.candidate_select.clear()
            for _,score in candidates:self.candidate_select.addItem(f"Candidate {score['candidate']+1}: {score['heuristic_rating']:.2f}")
            self.log('Bridge technical scores, not musical quality guarantees\n'+json.dumps([s for _,s in candidates],indent=2))
        self.work(task,callback=compared)

    def audition_candidate(self):
        index=self.candidate_select.currentIndex()
        if not 0<=index<len(self.transition_candidates) or self.player is None:return
        midi,_=self.transition_candidates[index];path=self.data_dir/f'candidate-{index}.wav'
        def rendered(path):
            self.render_path=None;self.audition=True;self.audition_label='Candidate';self.player.setSource(QUrl.fromLocalFile(str(path)));self.player.play()
        self.work(render_mix,copy.deepcopy(midi),path,None,self.soundfont or None,callback=rendered)

    def apply_candidate(self):
        index=self.candidate_select.currentIndex();transition=self.transition_select.currentIndex()
        if not 0<=index<len(self.transition_candidates):return
        transitions=self.report.get('transitions',[])
        if not 0<=transition<len(transitions):return
        record=transitions[transition];midi,score=self.transition_candidates[index]
        self.editor.replace_region(record['start'],record['end'],midi)
        record['manual_candidate']=score;self._edited();self.log('Replaced bridge notes; surrounding MIDI and controller data retained. Undo restores the previous bridge.')

    def mark_dirty(self):
        if self._building: return
        self.revision += 1; self.dirty = True
        self.setWindowTitle('TR1PP Mashup Studio 2.0 — '+self.project.title+' *')

    def bind_editor(self, editor):
        self.editor = editor; self.pm = editor.pm; self.project.midi = self.pm; self.project.sync_tracks()
        selected = max(0,self.track_select.currentIndex())
        self.track_select.blockSignals(True);self.track_select.clear()
        for ix, ins in enumerate(self.pm.instruments):self.track_select.addItem(ins.name or f'Track {ix+1}')
        self.track_select.setCurrentIndex(min(selected,len(self.pm.instruments)-1));self.track_select.blockSignals(False)
        self.roll.bind(editor,max(0,self.track_select.currentIndex())); self.timeline.bind(self.pm,self.report,self.project.markers)
        self.populate_mixer();self.update_grid()
        self.loop_end.setValue(self.pm.get_end_time());self.position.setRange(0,round(self.pm.get_end_time()*1000))
        if self.pm.instruments:
            # Start the viewport around the playable piano register.
            self.roll_scroll.verticalScrollBar().setValue((127-84)*self.roll.row_height)

    def _edited(self):
        if not self.editor:return
        self.stop_preview();self.render_path=None
        self.pm=self.editor.pm;self.project.midi=self.pm;self.project.sync_tracks()
        if self.track_select.count()!=len(self.pm.instruments):self.bind_editor(self.editor)
        else:
            self.roll.set_midi(self.pm);self.timeline.bind(self.pm,self.report,self.project.markers)
        self.mark_dirty();self.update_grid()
        self.position.setRange(0,round(self.pm.get_end_time()*1000))

    def select_track(self, index):
        if self.editor and index>=0:self.roll.bind(self.editor,index);self.roll.selection.clear();self.roll.update()

    def _edit_ready(self):
        if self.pm is None or not self.pm.instruments:
            self.log('Open a MIDI source or create a new track before adding notes.');return False
        return super()._edit_ready()

    def selected_indices(self):
        return sorted(self.roll.selection)

    def update_grid(self):
        if not hasattr(self,'grid_select'):return
        bpm=float(self.pm.get_tempo_changes()[1][0]) if self.pm else 120.
        subdivisions=[.25,.5,1,0]
        self.roll.grid = 60/bpm*subdivisions[self.grid_select.currentIndex()];self.roll.update()

    def new_track(self):
        if self.editor is None:self.editor=MidiEditor(self.project.midi)
        name,ok=QInputDialog.getText(self,'New track','Track name',text='Piano')
        if ok:
            ix=self.editor.add_track(name or 'Piano');self._edited();self.track_select.setCurrentIndex(ix)

    def edit_source(self):
        it=self.items.currentItem()
        if not it:return
        path=it.data(Qt.UserRole)
        if Path(path).suffix.lower() not in MIDI:return self.transcribe_selected()
        if not self.confirm_discard():return
        self.work(load,path,callback=lambda pm:self.source_loaded(pm,path))

    def source_loaded(self,pm,path):
        self.report={};self.project.report={};self.project.mixer=[];self.project.markers=[]
        self.bind_editor(MidiEditor(pm));self.transition_select.clear();self.clear_candidates();self.mark_dirty();self.log('Editing '+path)

    def preview_selected(self):
        it=self.items.currentItem()
        if not it:return
        if Path(it.data(Qt.UserRole)).suffix.lower() in MIDI:self.edit_source()
        else:self.inspect_waveform(play=True)

    def generated(self,result):
        pm,self.report=result
        self.report['source_signatures']=[hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in self.paths_now()]
        self.project.report=self.report;self.project.mixer=[]
        self.project.markers=[{'time':r['start'],'label':f"Source {r['source_index']+1}"} for r in self.report.get('source_regions',[])]
        self.bind_editor(MidiEditor(pm));self.transition_candidates=[];self.transition_select.clear();self.candidate_select.clear()
        for index,_ in enumerate(self.report.get('transitions',[])):self.transition_select.addItem(str(index+1))
        self.mark_dirty();self.log('Generated source-derived arrangement\n'+json.dumps(self.report,indent=2))

    def quantise_selection(self):
        if self.editor and self.roll.grid>0 and self.selected_indices():
            self.editor.transform(self.roll.track,self.selected_indices(),quantize=self.roll.grid);self._edited()

    def humanise_selection(self):
        if self.editor and self.selected_indices():
            self.editor.humanize(self.roll.track,self.selected_indices(),self.human.value());self._edited()

    def set_selection_velocity(self):
        if not self.editor or not self.selected_indices():return
        # One transaction, preserving all other note properties.
        self.editor.set_velocities(self.roll.track,self.selected_indices(),self.velocity.value());self._edited()

    def transpose_selection(self):
        if not self.editor or not self.selected_indices():return
        amount,ok=QInputDialog.getInt(self,'Transpose selection','Semitones',0,-127,127)
        if ok:self.editor.move_notes(self.roll.track,self.selected_indices(),transpose=amount);self._edited()

    def add_sustain(self):
        if not self.editor or not self.pm.instruments:return
        start=self.loop_start.value();end=self.loop_end.value()
        if end<=start:return self.log('Set loop From/To to a nonempty sustain region first.')
        self.editor.pedal(self.roll.track,start,end);self._edited()

    def split_hands(self):
        if self.editor:
            self.editor.assign_hands();self.project.mixer=[];self._edited()

    def change_tempo(self):
        if not self.editor:return
        bpm,ok=QInputDialog.getDouble(self,'Tempo','New initial BPM (scales entire tempo map)',float(self.pm.get_tempo_changes()[1][0]),20,400,2)
        if ok:
            ratio=float(self.pm.get_tempo_changes()[1][0])/bpm
            self.editor.set_tempo(bpm)
            # Generated source regions become stale after tempo edits.
            # User markers remain absolute-time anchors, including across MIDI undo.
            self.report={};self.project.report={};self._edited()

    def shift_track(self,index,delta):
        if self.editor:self.editor.shift_track(index,delta);self._edited()

    def add_marker(self):
        text,ok=QInputDialog.getText(self,'Timeline marker','Label')
        if ok and text:
            self.project.markers.append({'time':self.roll.cursor,'label':text});self.project.markers.sort(key=lambda m:m['time'])
            self.timeline.bind(self.pm,self.report,self.project.markers);self.mark_dirty()

    def populate_mixer(self):
        self.project.sync_tracks();self.mixer_table.setRowCount(len(self.pm.instruments))
        for ix,(ins,mix) in enumerate(zip(self.pm.instruments,self.project.mixer)):
            self.mixer_table.setItem(ix,0,QTableWidgetItem(ins.name or f'Track {ix+1}'))
            for column,field,lo,hi,value in [(1,'volume',0,2,mix.volume),(2,'pan',-1,1,mix.pan)]:
                spin=QDoubleSpinBox();spin.setRange(lo,hi);spin.setSingleStep(.05);spin.setValue(value)
                spin.valueChanged.connect(lambda v,i=ix,f=field:self.set_mix(i,f,v));self.mixer_table.setCellWidget(ix,column,spin)
            for column,field,value in [(3,'mute',mix.mute),(4,'solo',mix.solo)]:
                box=QCheckBox();box.setChecked(value);box.toggled.connect(lambda v,i=ix,f=field:self.set_mix(i,f,v));self.mixer_table.setCellWidget(ix,column,box)
            button=QPushButton(f'{len(mix.automation)} points · Edit')
            button.clicked.connect(lambda checked=False,i=ix:self.edit_automation(i));self.mixer_table.setCellWidget(ix,5,button)
            effects=QPushButton('Configure');effects.clicked.connect(lambda checked=False,i=ix:self.edit_effects(i));self.mixer_table.setCellWidget(ix,6,effects)
        self.mixer_table.resizeColumnsToContents()

    def set_mix(self,index,field,value):
        setattr(self.project.mixer[index],field,value);self.project.mixer[index].validate()
        self.stop_preview();self.render_path=None;self.mark_dirty()

    def edit_automation(self,index):
        mix=self.project.mixer[index];dialog=QDialog(self);dialog.setWindowTitle('Track gain automation')
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel('Click to add · Drag to move · Right-click to delete · Gain 0–2'))
        curve=AutomationCurve(mix.automation,self.pm.get_end_time());layout.addWidget(curve)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted:
            candidate=copy.deepcopy(mix);candidate.automation=sorted(curve.points);candidate.validate()
            self.project.mixer[index]=candidate;self.populate_mixer();self.stop_preview();self.render_path=None;self.mark_dirty()

    def edit_effects(self,index):
        mix=self.project.mixer[index];dialog=QDialog(self);dialog.setWindowTitle('Track render effects')
        form=QFormLayout(dialog);controls={}
        for key,label,low,high,step,default in [('lowpass_hz','Low-pass Hz (0 = off)',0,20000,100,0),('delay_mix','Delay amount',0,1,.05,0),('delay_seconds','Delay seconds',.02,2,.05,.25),('reverb_mix','Artificial room amount',0,1,.05,0)]:
            box=QDoubleSpinBox();box.setRange(low,high);box.setSingleStep(step);box.setValue(mix.effects.get(key,default));form.addRow(label,box);controls[key]=box
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            candidate=copy.deepcopy(mix);candidate.effects={key:box.value() for key,box in controls.items()};candidate.validate()
            self.project.mixer[index]=candidate;self.stop_preview();self.render_path=None;self.mark_dirty()

    def capture_project(self):
        self.project.midi=self.pm if self.pm is not None else self.project.midi
        self.project.sources=[self.source_origins.get(p,p) for p in self.paths_now()];self.project.settings=vars(self.settings());self.project.report=self.report
        self.project.settings['structure']=self.structure.currentText()
        if self.custom_plan is not None:
            from dataclasses import asdict
            self.project.settings['custom_plan']=asdict(self.custom_plan)
        self.project.sync_tracks();return copy.deepcopy(self.project)

    def confirm_discard(self):
        if not self.dirty:return True
        return QMessageBox.question(self,'Unsaved changes','Replace the current edit? Save first to keep it. A recovery snapshot will be retained.',QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes and bool(self.manual_snapshot())

    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'Save portable project',str(self.project_path or 'TR1PP project.tr1pp'),'TR1PP project (*.tr1pp)')
        if not path:return
        if not path.lower().endswith('.tr1pp'):path+='.tr1pp'
        current=self.revision;project=self.capture_project();project.title=Path(path).stem
        def saved(result):
            self.project_path=Path(result);self.project.title=project.title
            if current==self.revision:self.dirty=False;self.setWindowTitle('TR1PP Mashup Studio 2.0 — '+self.project.title)
            self.log('Saved self-contained project '+str(result))
        def persist():
            history=self.data_dir/'history'/hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:16]
            if Path(path).is_file():snapshot(load_project(path),history,keep=20)
            result=save_project(project,path);snapshot(project,history,keep=20);return result
        self.work(persist,callback=saved)

    def open_project(self):
        if not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,'Open project','','TR1PP (*.tr1pp *.json)')
        if path:self.load_project_path(path)

    def load_project_path(self,path):
        def task():
            project=load_project(path);paths=materialize_sources(project,self.data_dir/'sources',strict=False)
            return project,paths
        def opened(result):
            project,paths=result;self.project=project;self.project_path=Path(path);self.report=project.report
            self.items.clear()
            self.source_origins={new:old for old,new in zip(project.sources,paths)}
            self._building=True
            try:
                for source in paths:self.add_item(source)
                settings=project.settings
                self.style.setCurrentText(settings.get('mode','Seamless Transition'))
                self.bridge.setValue(settings.get('bridge_bars',8));self.cross.setValue(settings.get('crossfade_bars',4))
                self.bpm.setValue(settings.get('target_bpm',0));self.human.setValue(int(settings.get('humanize_ms',7)))
                self.structure.setCurrentText(settings.get('structure','Complete sources + bridges'))
                self.custom_plan=ArrangementPlan.from_dict(settings['custom_plan']) if settings.get('custom_plan') else None
                self.difficulty.setValue(settings.get('difficulty',65));self.strict.setChecked(settings.get('strict_two_hands',True))
                self.bind_editor(MidiEditor(project.midi))
                self.transition_candidates=[];self.transition_select.clear();self.candidate_select.clear()
                for index,_ in enumerate(self.report.get('transitions',[])):self.transition_select.addItem(str(index+1))
            finally:self._building=False
            self.dirty=False;self.render_path=None;self.stop_preview()
            self.setWindowTitle('TR1PP Mashup Studio 2.0 — '+project.title);self.log('Opened portable project '+str(path))
        self.work(task,callback=opened)

    def manual_snapshot(self):
        if self.pm is None:return None
        try:
            path=snapshot(self.capture_project(),self.data_dir/'recovery');self.log('Snapshot saved '+path.name);return path
        except Exception as e:self.log('Recovery save failed: '+str(e));return None

    def autosave(self):
        if self.dirty and not (self.worker and self.worker.isRunning()):
            project=self.capture_project()
            self.work(snapshot,project,self.data_dir/'recovery',callback=lambda path:self.log('Recovery snapshot: '+path.name))

    def recover_project(self):
        if not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,'Recover snapshot',str(self.data_dir/'recovery'),'TR1PP (*.tr1pp)')
        if path:self.load_project_path(path)

    def choose_soundfont(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose piano SF2 (Cancel keeps current)','','SoundFont (*.sf2)')
        if path:
            self.soundfont=path;self.preferences.setValue('soundfont',path);self.preferences.sync();self.render_path=None;self.stop_preview();self.log('SoundFont selected '+Path(path).name)

    def play_preview(self):
        self.audition=False
        if self.pm is None or not any(i.notes for i in self.pm.instruments):return self.no_output()
        if self.player is None:return self.log('Qt Multimedia backend unavailable; render audio to audition externally.')
        if self.render_path and self.render_revision==self.revision and Path(self.render_path).is_file():
            self.player.play();return
        revision=self.revision;start=self.roll.cursor
        path=self.data_dir/f'preview-{revision}.wav'
        def rendered(result):
            if revision!=self.revision:return self.log('Preview discarded because the MIDI or mixer changed during rendering.')
            self.render_path=result;self.render_revision=revision
            self.player.setSource(QUrl.fromLocalFile(str(Path(result).resolve())));self.player.setPosition(round(start*1000));self.player.play()
            self.log('Preview: '+('SoundFont piano' if self.soundfont else 'synthetic pitched instrument'))
        self.work(render_mix,copy.deepcopy(self.pm),path,copy.deepcopy(self.project.mixer),self.soundfont or None,callback=rendered)

    def toggle_playback(self):
        if self.player is not None:
            from PySide6.QtMultimedia import QMediaPlayer
            if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause();return
        self.play_preview()

    def stop_preview(self):
        if self.player is not None:self.player.stop()

    def seek(self,seconds):
        seconds=max(0,float(seconds));self.roll.cursor=seconds;self.timeline.cursor=seconds
        self.roll.update();self.timeline.update();self.position.setValue(round(seconds*1000))
        if self.player is not None and self.render_path:self.player.setPosition(round(seconds*1000))

    def playback_position(self,milliseconds):
        seconds=milliseconds/1000
        if self.audition:
            self.time_label.setText(f'{getattr(self,"audition_label","Audition")}: {seconds:.2f} s');return
        if self.loop.isChecked() and self.loop_end.value()>self.loop_start.value() and seconds>=self.loop_end.value():
            self.player.setPosition(round(self.loop_start.value()*1000));return
        self.roll.cursor=seconds;self.timeline.cursor=seconds;self.roll.update();self.timeline.update()
        if not self.position.isSliderDown():self.position.setValue(milliseconds)
        self.time_label.setText(f'{seconds:.2f} / {self.position.maximum()/1000:.2f} s')

    def media_status(self,status):
        from PySide6.QtMultimedia import QMediaPlayer
        if not self.audition and status==QMediaPlayer.EndOfMedia and self.loop.isChecked() and self.loop_end.value()>self.loop_start.value():
            self.player.setPosition(round(self.loop_start.value()*1000));self.player.play()

    def device_changed(self,index):
        device=self.devices.itemData(index)
        if hasattr(self,'audio_output'):
            from PySide6.QtMultimedia import QMediaDevices
            self.audio_output.setDevice(device if device is not None else QMediaDevices.defaultAudioOutput())

    def export_audio(self):
        if self.pm is None:return self.no_output()
        path,_=QFileDialog.getSaveFileName(self,'Export current mix','TR1PP mix.wav','WAV (*.wav);;FLAC (*.flac);;MP3 (*.mp3)')
        if path:self.work(render_mix,copy.deepcopy(self.pm),path,copy.deepcopy(self.project.mixer),self.soundfont or None,callback=lambda p:self.log('Exported mix '+str(p)))

    def export_stem_files(self):
        if self.pm is None:return self.no_output()
        folder=QFileDialog.getExistingDirectory(self,'Export one WAV per MIDI track')
        if folder:self.work(export_stems,copy.deepcopy(self.pm),folder,copy.deepcopy(self.project.mixer),self.soundfont or None,callback=lambda paths:self.log('Exported '+str(len(paths))+' stems'))

    def configure_transcription(self):
        current=self.transcription_options
        text,ok=QInputDialog.getMultiLineText(self,'Transcription options','Model thresholds, note filtering, piano range, maximum duration',json.dumps(vars(current),indent=2))
        if not ok:return
        try:
            options=TranscriptionOptions(**json.loads(text));options.validate();self.transcription_options=options
        except (ValueError,TypeError) as e:QMessageBox.warning(self,'Invalid transcription settings',str(e))

    def transcribe_selected(self):
        it=self.items.currentItem()
        if not it:return self.log('Select an audio/video source to transcribe.')
        path=it.data(Qt.UserRole)
        if Path(path).suffix.lower() in MIDI:return self.edit_source()
        if not self.confirm_discard():return
        def completed(info):
            row=next((i for i in range(self.items.count()) if self.items.item(i).data(Qt.UserRole)==path),-1)
            # Replace the active source with its editable MIDI; retain source audio
            # as an embedded provenance asset in the portable project.
            self.project.assets[path]=Path(path).read_bytes()
            if row>=0:self.items.takeItem(row)
            self.project.source_names[info['midi_path']]=Path(path).stem+' (transcribed).mid'
            self.add_item(info['midi_path'])
            pm=load(info['midi_path']);self.source_loaded(pm,path)
            self.report={'transcription':info,'analysis':analyse(pm)};self.project.report=self.report
            self.log(f"Transcribed {len(info['notes'])} notes · mean model activation {info['mean_activation']:.3f}\n"+info['message'])
        self.work(transcribe,path,self.data_dir/'transcriptions',self.transcription_options,callback=completed)

    def inspect_waveform(self,play=False):
        it=self.items.currentItem()
        if not it:return
        path=it.data(Qt.UserRole)
        if Path(path).suffix.lower() in MIDI:return self.edit_source()
        def task():
            preview_dir=self.data_dir/'source-previews';preview_dir.mkdir(exist_ok=True)
            import uuid
            wav=preview_dir/(uuid.uuid4().hex+'.wav');decode_audio(path,wav,self.transcription_options.max_seconds)
            data=waveform(wav);data['path']=str(wav);return data
        def finished(data):
            self.wave.data=data;self.wave.update();self.tabs.setCurrentWidget(self.wave)
            if play and self.player is not None:
                self.stop_preview();self.render_path=None;self.audition=True;self.audition_label='Source'
                self.player.setSource(QUrl.fromLocalFile(data['path']));self.player.play()
        self.work(task,callback=finished)

    def batch_urls(self):
        text,ok=QInputDialog.getMultiLineText(self,'Import URLs','One supported HTTPS YouTube/Vimeo URL per line')
        if not ok:return
        urls=[line.strip() for line in text.splitlines() if line.strip()]
        def task():
            results=[]
            for url in urls:
                try:results.append({'url':url,'path':acquire(url,self.data_dir/'imports')})
                except Exception as e:results.append({'url':url,'error':str(e)})
            return results
        def completed(results):
            for result in results:
                if result.get('path'):self.add_item(result['path'])
                else:self.log('URL import failed: '+result['url']+' · '+result['error'])
        if urls:self.work(task,callback=completed)

    def add_item(self,path):
        count=self.items.count();super().add_item(path)
        if self.items.count()>count:
            original=self.source_origins.get(str(path),str(path))
            name=self.project.source_names.setdefault(original,Path(path).name)
            self.items.item(self.items.count()-1).setText(name)
        self.mark_dirty()

    def remove_file(self):super().remove_file();self.mark_dirty()
    def move(self,d):super().move(d);self.mark_dirty()

    def work(self,fn,*args,callback):
        if self.worker is not None and self.worker.isRunning():
            self.log('A task is already running; wait for it to finish.');return False
        worker=Worker(fn,*args);self.worker=worker;self.jobs.append(worker)
        self.progress.setRange(0,0);state={}
        self.centralWidget().setEnabled(False)
        for bar in self.findChildren(QToolBar):bar.setEnabled(False)
        worker.done.connect(lambda result:state.update(result=result))
        worker.failed.connect(lambda error:state.update(error=error))
        def finished():
            self.centralWidget().setEnabled(True)
            if self.workflow_dialog is not None:self.workflow_dialog.close();self.workflow_dialog=None
            for bar in self.findChildren(QToolBar):bar.setEnabled(True)
            self.progress.setRange(0,100);self.progress.setValue(0 if 'error' in state else 100)
            if worker in self.jobs:self.jobs.remove(worker)
            if self.worker is worker:self.worker=None
            worker.deleteLater()
            try:
                if 'error' in state:
                    error=state['error'];self.log(error)
                    if 'WorkflowCancelled' not in error:QMessageBox.warning(self,'Task failed',error.splitlines()[-1])
                elif 'result' in state:callback(state['result'])
            except Exception:
                import traceback
                self.log(traceback.format_exc());QMessageBox.warning(self,'Operation failed',traceback.format_exc().splitlines()[-1])
        worker.finished.connect(finished);worker.start();return True

    def closeEvent(self,event):
        if self.worker is not None and self.worker.isRunning():
            self.log('A task is running. Close the window after it finishes.');event.ignore();return
        if self.dirty:
            result=QMessageBox.question(self,'Unsaved project','Save a recovery snapshot and close?',QMessageBox.Yes|QMessageBox.No)
            if result!=QMessageBox.Yes or self.manual_snapshot() is None:event.ignore();return
        self.stop_preview();self.autosave_timer.stop();event.accept()


def run():
    app=QApplication(sys.argv);app.setApplicationName('TR1PP Mashup Studio')
    window=StudioWindow();window.show();sys.exit(app.exec())
