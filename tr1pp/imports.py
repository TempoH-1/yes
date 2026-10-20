"""Source acquisition: URL validation, metadata, explicit download and audio transcription."""
from pathlib import Path
from urllib.parse import urlparse
import shutil

AUDIO={'.wav','.mp3','.flac','.ogg','.m4a','.mp4','.webm','.aac','.aif','.aiff','.wma','.mov','.mkv','.avi','.m4v','.opus'}
MIDI={'.mid','.midi'}

def validate_url(url):
    p=urlparse(url.strip())
    if p.scheme!='https' or not p.hostname:raise ValueError('Use an HTTPS video URL')
    domain=p.hostname.lower().removeprefix('www.')
    allowed=('youtube.com','youtu.be','music.youtube.com','vimeo.com')
    if domain not in allowed:
        import ipaddress
        if Path(p.path).suffix.lower() not in AUDIO:raise ValueError('Use YouTube, Vimeo, or a direct HTTPS audio/video URL')
        if domain in ('localhost',) or domain.endswith(('.localhost','.local')):raise ValueError('Use a public media hostname')
        try:
            address=ipaddress.ip_address(domain)
        except ValueError:address=None
        if address is not None and not address.is_global:raise ValueError('Private network media URLs are not supported')
    if p.username or p.password:raise ValueError('Embedded credentials are not supported')
    return url.strip()

def metadata(url):
    url=validate_url(url)
    try:from yt_dlp import YoutubeDL
    except ImportError as e:raise RuntimeError('yt-dlp missing. Re-run setup.bat or pip install yt-dlp') from e
    with YoutubeDL({'quiet':True,'no_warnings':True,'skip_download':True,'noplaylist':True,'socket_timeout':20}) as dl:
        data=dl.extract_info(url,download=False)
    if not data:raise RuntimeError('This URL did not return public video metadata')
    return {'title':data.get('title','Untitled'),'duration':data.get('duration'), 'uploader':data.get('uploader'),'url':url,'extractor':data.get('extractor')}

def acquire(url,directory):
    url=validate_url(url)
    try:from yt_dlp import YoutubeDL
    except ImportError as e:raise RuntimeError('Install yt-dlp for authorised media imports') from e
    if not shutil.which('ffmpeg'):raise RuntimeError('FFmpeg is required for video audio extraction. Install FFmpeg and add it to PATH.')
    target=Path(directory);target.mkdir(parents=True,exist_ok=True)
    opts={'format':'bestaudio/best','outtmpl':str(target/'%(title).120s-%(id)s.%(ext)s'),
       'noplaylist':True,'quiet':True,'no_warnings':True,'socket_timeout':30,
       'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'wav'}]}
    with YoutubeDL(opts) as dl:
        data=dl.extract_info(url,download=True)
        original=Path(dl.prepare_filename(data));converted=original.with_suffix('.wav')
        if converted.exists():return str(converted)
    raise RuntimeError('Audio conversion finished without a WAV file. Check FFmpeg output.')

def extract_local_audio(path,directory):
    """Decode to a content-addressed mono WAV without overwriting source media."""
    import hashlib
    from .transcription import decode_audio
    source=Path(path);target=Path(directory);target.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256()
    with source.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    output=target/(digest.hexdigest()+'-mono.wav')
    if output.resolve()==source.resolve():raise ValueError('Decoded output must differ from source')
    decode_audio(source,output)
    return str(output)

def transcribe_audio(path,directory):
    """Backward-compatible entry point for the verified ONNX transcription path."""
    from .transcription import transcribe
    return transcribe(path,directory)
