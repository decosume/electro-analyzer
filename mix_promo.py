from pydub import AudioSegment

voice = AudioSegment.from_file('promo_voice.mp3')
bed = AudioSegment.from_file('background_music.mp3')

bed = bed[:len(voice)]
bed = bed - 8
mixed = bed.overlay(voice)
mixed.export('promo_clip.mp3', format='mp3')
print('Created promo_clip.mp3')
