from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
from tr1pp.imports import extract_local_audio,validate_url
from tr1pp.transcription import decode_audio


def test_local_decode_is_content_addressed_and_preserves_sources(tmp_path):
    output=tmp_path/'decoded';sources=[]
    for index,hz in enumerate((220,440)):
        directory=tmp_path/str(index);directory.mkdir();source=directory/'same-name.wav'
        time=np.arange(16000)/16000
        sf.write(source,np.column_stack([.2*np.sin(2*np.pi*hz*time)]*2),16000)
        before=source.read_bytes();result=Path(extract_local_audio(source,output))
        info=sf.info(result)
        assert info.channels==1 and info.samplerate==22050
        assert source.read_bytes()==before
        sources.append(result)
    assert sources[0]!=sources[1]
    assert validate_url('https://example.com/audio.wav')=='https://example.com/audio.wav'


def test_real_local_video_audio_import(tmp_path):
    source=tmp_path/'tone.wav';sr=22050;t=np.arange(sr)/sr
    sf.write(source,.2*np.sin(2*np.pi*440*t),sr)
    video=tmp_path/'video.mp4'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=c=black:s=64x64:r=1:d=1',
                    '-i',str(source),'-shortest','-c:v','mpeg4','-c:a','aac',str(video)],check=True,capture_output=True)
    info=decode_audio(video,tmp_path/'decoded.wav')
    assert info['channels']==1 and info['sample_rate']==22050 and info['duration']>.8
    audio,_=sf.read(tmp_path/'decoded.wav');assert np.max(np.abs(audio))>.05
