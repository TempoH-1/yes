from pathlib import Path
import pretty_midi
root=Path(__file__).resolve().parent/'fixtures';root.mkdir(exist_ok=True)
for idx,melody in enumerate(([64,68,71,76,71,68,64,71],[67,69,71,74,76,74,71,69]),1):
    pm=pretty_midi.PrettyMIDI(initial_tempo=140)
    rh=pretty_midi.Instrument(0,name='Synthetic melody')
    lh=pretty_midi.Instrument(0,name='Synthetic bass')
    for cycle in range(8):
        for beat,p in enumerate(melody):
            t=(cycle*8+beat)*.215
            rh.notes.append(pretty_midi.Note(95,p,t,t+.18))
            if beat%2==0:lh.notes.append(pretty_midi.Note(65,p-24,t,t+.35))
    pm.instruments=[rh,lh]
    pm.write(str(root/f'Demo Source {idx}.mid'))
print('Created demonstration MIDI sources (synthetic, not Rush E or Gladiators).')
