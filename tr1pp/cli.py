"""Repeatable studio workflows without requiring a desktop/audio device."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser(prog='tr1pp',description='TR1PP Mashup Studio 2.0 development tools')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('gui',help='Launch the PySide6 studio')
    commands.add_parser('doctor',help='Report runtime capabilities without displaying credentials')
    analyze=commands.add_parser('analyse');analyze.add_argument('midi')
    transcribe=commands.add_parser('transcribe');transcribe.add_argument('audio');transcribe.add_argument('--output-dir',required=True)
    build=commands.add_parser('build',help='Import audio/MIDI/URLs, analyse, arrange, save a portable project')
    build.add_argument('sources',nargs='+');build.add_argument('--project',required=True)
    build.add_argument('--cache-dir',default='.tr1pp-cache')
    build.add_argument('--structure',choices=['Complete sources + bridges','A/B/A thematic','Layered motifs','Call and response'],default='Complete sources + bridges')
    build.add_argument('--bpm',type=float,default=0);build.add_argument('--difficulty',type=int,default=65)
    build.add_argument('--bridge-bars',type=int,default=8);build.add_argument('--midi')
    render=commands.add_parser('render');render.add_argument('project');render.add_argument('output');render.add_argument('--soundfont')
    args=parser.parse_args(argv)
    try:
        if args.command=='gui':
            from .studio import run
            run();return 0
        if args.command=='doctor':
            from .runtime import diagnose
            print(json.dumps(diagnose(),indent=2));return 0
        if args.command=='analyse':
            from .engine import load,analyse
            from .planning import harmonic_timeline
            midi=load(args.midi);print(json.dumps({'analysis':analyse(midi),'harmony':harmonic_timeline(midi)},indent=2));return 0
        if args.command=='transcribe':
            from .transcription import transcribe
            result=transcribe(args.audio,args.output_dir,progress=lambda n,m:print(f'{n}% {m}',file=sys.stderr))
            print(json.dumps(result,indent=2));return 0
        if args.command=='build':
            from .workflow import prepare_project
            from .engine import Settings
            from .project import save_project
            settings=Settings(target_bpm=args.bpm,difficulty=args.difficulty,bridge_bars=args.bridge_bars)
            project=prepare_project(args.sources,args.cache_dir,settings,args.structure,progress=lambda n,m:print(f'{n}% {m}',file=sys.stderr))
            save_project(project,args.project)
            if args.midi:project.midi.write(args.midi)
            errors=project.report['import_workflow']['errors']
            print(json.dumps({'project':str(Path(args.project).resolve()),'sources':len(project.sources),
                              'tracks':len(project.midi.instruments),'errors':errors},indent=2))
            return 2 if errors else 0
        if args.command=='render':
            from .project import load_project
            from .audio import render_mix
            project=load_project(args.project)
            output=render_mix(project.midi,args.output,project.mixer,args.soundfont)
            print(output);return 0
    except Exception as e:
        print(f'{type(e).__name__}: {e}',file=sys.stderr);return 1
    return 0
