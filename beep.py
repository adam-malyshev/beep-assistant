#!/usr/bin/env python3

import struct
import pvporcupine
import pyaudio
import wave
import openai
from gtts import gTTS
import time
import os
import math
import sys
import google.cloud.texttospeech as tts
access_key = "uB/jLDdUQ96x8ha/8w/Yq71qUFo61ByJcfvQqJirOnbAKoq62tW+Tg=="
lang = sys.argv[1] or "en"
name = "Beep"

voices = {
    "en":"en-GB-Neural2-D",
    "ru":"ru-RU-Wavenet-B"
}


keyword_paths = ["/home/beep/beep-assistant/wake/Sunshine.ppn", "/home/beep/beep-assistant/wake/HeyBeep.ppn"]
#["/home/beep/wake/MyJoyRu.ppn"]
 
            
def record(audio, stream, sample_rate, chunk, seconds, output_file="input.wav", chans=1, form_1=pyaudio.paInt16):
    print("Listening....")
    frames = []

    # loop through stream and append audio chunks to frame array
    for ii in range(0,int((sample_rate/chunk)*seconds)):
        data = stream.read(chunk, exception_on_overflow = False)
        frames.append(data)

    print("Finished Recording")

    # save the audio frames as .wav file
    wavefile = wave.open(output_file,'wb')
    wavefile.setnchannels(chans)
    wavefile.setsampwidth(audio.get_sample_size(form_1))
    wavefile.setframerate(sample_rate)
    wavefile.writeframes(b''.join(frames))
    wavefile.close() 


    
def transcribe(file):
    audio_file= open(file, "rb")
    transcript = openai.Audio.transcribe("whisper-1", audio_file) #in the form {"text":...}
    print("Transcribed:", transcript.text)
    return transcript.text

def respond(text):
    completion = openai.ChatCompletion.create(
        model = "gpt-3.5-turbo",
        temperature = 0.8,
        max_tokens = 1000,
        messages = [
            {"role": "system", "content": f"You are {name}, a helpful assitant meant for children in elementary school. You answer the questions of children in an easy to understand and fun way."},
            {"role": "user", "content": "Why is the sky blue?"},
            {"role": "assistant", "content": "The light from the sun goes through many many layers of air. The air is made up of tiny molecules. The sun's white light is made up of a bunch of colors, and blue is the only one that bumps into these molecules. This bumping spreads it out across the sky making it look blue."},
            {"role": "user", "content": text}
        ]
    )
    print("Responded:", completion.choices[0].message) 
    return completion.choices[0].message.content


def speak(text, language): 
    # Language in which you want to convert
      
    # Passing the text and language to the engine,
    # here we have marked slow=False. Which tells 
    # the module that the converted audio should 
    # have a high speed
    tts = gTTS(text=text, lang=language, slow=False)     
    # Saving the converted audio in a mp3 file named
    # output 
    tts.save("output.mp3")
      
    # Playing the converted file
    os.system("mpg123 output.mp3")
    print("speaking")



def text_to_wav(voice_name: str, text: str):
    language_code = "-".join(voice_name.split("-")[:2])
    text_input = tts.SynthesisInput(text=text)
    voice_params = tts.VoiceSelectionParams(
        language_code=language_code, name=voice_name
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)

    client = tts.TextToSpeechClient()
    response = client.synthesize_speech(
        input=text_input,
        voice=voice_params,
        audio_config=audio_config,
    )

    filename = "output.wav"
    with open(filename, "wb") as out:
        out.write(response.audio_content)
        print(f'Generated speech saved to "{filename}"')
    os.system(f"aplay {filename}")
    

porcupine = None
pa = None
audio_stream = None

try:
    porcupine = pvporcupine.create(access_key=access_key, keyword_paths=keyword_paths)
    #porcupine = pvporcupine.create(access_key=access_key, keyword_paths=["/home/beep/wake/MyJoyRu.ppn"])
    #a = Audio(1, porcupine.sample_rate, porcupine.frame_length, "input.wav")
    pa = pyaudio.PyAudio()
    audio_stream = pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length)
    print("intialized")
    while(True):
        pcm = audio_stream.read(porcupine.frame_length, exception_on_overflow = False)
        pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)
        keyword_index = porcupine.process(pcm)

        if keyword_index >= 0:
            print("Keyword Detected")
            record(
                audio=pa,
                stream=audio_stream, 
                sample_rate=porcupine.sample_rate, 
                chunk=porcupine.frame_length, 
                seconds=5)

            text = transcribe("input.wav")
            response = respond(text)
            #speak(response, lang)
            text_to_wav(voices[lang], response)
finally:
    if porcupine is not None:
        porcupine.delete()
    if audio_stream is not None:
        audio_stream.close()
    if pa is not None:
        pa.terminate()

