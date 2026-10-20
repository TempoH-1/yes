"""Conservative recovery for MIDI files with high-bit channel data bytes.

Only bytes in channel-message DATA positions are changed. Status, SysEx,
meta event bodies and VLQ lengths remain untouched. Original is never altered.
"""
from pathlib import Path

class MIDIRepairError(ValueError): pass

def _vlq(buf, pos, end):
    number=0
    for _ in range(4):
        if pos>=end:raise MIDIRepairError('Truncated MIDI variable-length value')
        b=buf[pos];pos+=1;number=(number<<7)|(b&127)
        if not (b&128):return number,pos
    raise MIDIRepairError('Unsupported variable-length MIDI field')

def repair_bytes(blob):
    data=bytearray(blob)
    if data[:4]!=b'MThd' or len(data)<14:raise MIDIRepairError('Not a standard MIDI header')
    header_len=int.from_bytes(data[4:8],'big')
    if header_len<6 or 8+header_len>len(data):raise MIDIRepairError('Invalid MIDI header length')
    pos=8+header_len;fixed=[];tracknum=0
    while pos<len(data):
        if pos+8>len(data):raise MIDIRepairError('Truncated MIDI chunk')
        tag=data[pos:pos+4];length=int.from_bytes(data[pos+4:pos+8],'big');pos+=8;end=pos+length
        if end>len(data):raise MIDIRepairError('MIDI chunk length exceeds file')
        if tag!=b'MTrk':pos=end;continue
        tracknum+=1;running=None
        while pos<end:
            _,pos=_vlq(data,pos,end)
            if pos>=end:raise MIDIRepairError('Truncated event')
            status=data[pos]
            if status>=128:
                pos+=1
                if status==255:
                    if pos>=end:raise MIDIRepairError('Missing meta type')
                    pos+=1;size,pos=_vlq(data,pos,end);pos+=size
                    if pos>end:raise MIDIRepairError('Truncated meta event')
                    continue
                if status in (240,247):
                    size,pos=_vlq(data,pos,end);pos+=size
                    if pos>end:raise MIDIRepairError('Truncated SysEx')
                    running=None;continue
                if 128<=status<=239:running=status
                else:raise MIDIRepairError('Unexpected MIDI status byte')
            elif running is None:raise MIDIRepairError('Missing running status')
            status=running
            needed=1 if (status&240) in (192,208) else 2
            if pos+needed>end:raise MIDIRepairError('Truncated channel event')
            for _ in range(needed):
                if data[pos]>127:
                    fixed.append({'track':tracknum,'byte_offset':pos,'before':data[pos],'after':data[pos]&127})
                    data[pos]&=127
                pos+=1
    return bytes(data),fixed

def recover_midi(path):
    import pretty_midi
    from io import BytesIO
    path=Path(path)
    try:return pretty_midi.PrettyMIDI(str(path)),[]
    except (OSError,ValueError,IndexError,EOFError) as original:
        try:
            result,changes=repair_bytes(path.read_bytes())
            if not changes:raise MIDIRepairError('No safe channel-data repair identified')
            pm=pretty_midi.PrettyMIDI(BytesIO(result))
            return pm,changes
        except Exception as failure:
            raise MIDIRepairError(f'{path.name}: MIDI parser rejected this file ({original}); safe recovery failed: {failure}') from failure
