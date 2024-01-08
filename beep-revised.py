from time import sleep
import sys
import pyaudio
import multiprocessing as mp
import logging
import wave
import math
import struct
import pvporcupine
import openai
import google.cloud.texttospeech as tts
from datetime import datetime, timedelta
import audioop
import io
import os
import dotenv
import traceback
class Beep:

    def __init__(self, input_device_index=None, output_device_index=None, lang="en", dBthreshold=10):
        ACCESS_KEY = "uB/jLDdUQ96x8ha/8w/Yq71qUFo61ByJcfvQqJirOnbAKoq62tW+Tg==" 
        KEYWORDS = ["/home/beep/beep-assistant/wake/Sunshine.ppn", "/home/beep/beep-assistant/wake/HeyBeep.ppn"]
        self.porcupine = pvporcupine.create(access_key=ACCESS_KEY, keyword_paths=KEYWORDS)
        self.RATE = self.porcupine.sample_rate
        
        #self.RATE = 44100
        self.CHUNK = self.porcupine.frame_length
        print("Sample Width: ", self.CHUNK)
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        self.channels=1
        self._pa = pyaudio.PyAudio()
        self.stream = self._pa.open(
                rate=self.RATE,
                channels=self.channels, 
                format=pyaudio.paInt16, 
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.CHUNK)
        self.p_out = pyaudio.PyAudio()
        self.stream_out = self.p_out.open(format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.RATE,
                        output=True,
                        output_device_index=self.output_device_index)

        self.thread = mp.Process(name='_collect_data', target=self._collect_data) 
        self.frames = mp.Queue()
        self.voices =  {
            "en":"en-GB-Neural2-D",
            "ru":"ru-RU-Wavenet-B"
        }
        self.logger = mp.log_to_stderr()
        self.logger.setLevel(logging.INFO)
        self.temp_file = "/home/beep/beep-assistant/audio/input.wav"
        self.name = "Beep"
        self.lang = lang
        self.SSML = True
        self.max_input_seconds=20
        self.speech_buffer_seconds=5
        self.dBthreshold= dBthreshold
        self.detectionVolume= 50 + self.dBthreshold
    def get(self):
        return self.frames.get()
    def empty(self):
        return self.frames.empty()
    def full(self):
        return self.frames.full()
    def put(self, data):
        self.frames.put(data)
    def length(self):
        return self.frames.qsize()
    def volume(self, audio_data):
        rms = audioop.rms(audio_data, 2)
        if rms > 0:
            dB = 20 * math.log10(rms)
        else:
            dB = 0
        #self.logger.info("dB: ",dB)
        return dB 
    
    def isSpeech(self, audio_data):
        return self.volume(audio_data) > self.detectionVolume
    
    def avg_volume(self, seconds):
        sum_vol =  self.volume(self.stream.read(self.CHUNK, exception_on_overflow = False))
        start = datetime.utcnow()
        now = start
        i = 1
        while (now - start) < timedelta(seconds= seconds):
            now = datetime.utcnow()
            i += 1
            sum_vol += self.volume(self.stream.read(self.CHUNK, exception_on_overflow = False))
        return sum_vol/i


    def start(self):
        self.thread.start()
    
    def terminate(self):
        self.thread.terminate()

    def _collect_data(self):
        self.logger.info("called")
        try:
            self.logger.info("started")

            self.logger.info('Audio Stream started')
            
            self.play_sound("/home/beep/beep-assistant/audio/startup.wav")
            last_speech = datetime.utcnow()        
            record = False
            wake_detected = datetime.utcnow()
            responder = mp.Process(name= 'Responder', target = self.record_callback)
            responder.start()
            
            self.detectionVolume = self.avg_volume(5) + self.dBthreshold
            self.logger.info(f'detectionVolume {self.detectionVolume}')
            while True:
                now = datetime.utcnow()
                delta = now - last_speech
                raw_data = self.stream.read(self.CHUNK, exception_on_overflow = False)
                audio_data = struct.unpack_from("h" * self.CHUNK, raw_data)
                keyword_index = self.porcupine.process(audio_data)
                if (now - last_speech) % timedelta(seconds=5) == timedelta(seconds=0):
                    print("listening")
                if keyword_index >= 0:
                    self.logger.info("wake word detected")
                    print("wake detected")
                    record = True
                    last_speech = now
                    wake_detected = now
                    responder.terminate()
                    self.play_sound("/home/beep/beep-assistant/audio/beep-07a.wav")
                elif (delta > timedelta(seconds=self.speech_buffer_seconds) or now - wake_detected > timedelta(seconds=self.max_input_seconds)) and record:
                    self.logger.info("starting to record")
                    record = False
                    responder = mp.Process(name='Responder', target=self.record_callback)
                    responder.start()
                elif self.isSpeech(raw_data) and record:
                    self.logger.info(".")
                    last_speech = now
                    self.put(raw_data)

        except Exception as e:
            self.logger.exception(e)
            os.system(f'espeak {e}')
            #self.play_sound("/home/beep/beep-assistant/audio/error.wav")
        finally:
            self.logger.warning('Audio Stream Loop exited')
            self.stream.close()
            self.porcupine.delete()
            self._pa.terminate()
            self.p_out.terminate()
            self.stream_out.close()




    def record_callback(self):
        try:
            self.logger.info('Started Processing process')
            if not self.empty():
                self.logger.info("Writing audio")
                clip = []
                frames = 0
                while not self.empty():
                    clip.append(self.get())
                    frames += 1
                with wave.open(self.temp_file, 'wb') as f:
                    f.setnchannels(self.channels)
                    f.setsampwidth(self._pa.get_sample_size(pyaudio.paInt16))
                    f.setframerate(self.RATE)
                    f.writeframes(b''.join(clip))
                self.play_sound("/home/beep/beep-assistant/audio/beep-02.wav")
                text = self.transcribe(self.temp_file)
                response = self.respond(text)
                self.text_to_wav(self.voices[self.lang], response) 
        except Exception as e:
            self.logger.warning(e)
            self.play_sound("/home/beep/beep-assistant/audio/error.wav")
        finally:
            self.logger.warning('writing stopped')

    def transcribe(self, file):
        try:
            self.logger.info('transcription started')

            audio_file= open(file, "rb")
            transcript = openai.Audio.transcribe("whisper-1", audio_file) #in the form {"text":...}
            print("Transcribed:", transcript.text)
            return transcript.text
        except Exception as e:
            self.logger.warning(e)
            self.play_sound("/home/beep/beep-assistant/audio/error.wav")
        finally:
            self.logger.warning('transcription exited')
 
    def respond(self, text):
        try:
            self.logger.info('Response started')
            ssml = ('You are connected to a text-to-speech software so you output responses formatted properly in SSML.' if self.SSML else '') 
            completion = openai.ChatCompletion.create(
                model = "gpt-3.5-turbo",
                temperature = 0.8,
                max_tokens = 1000,
                messages = [
                    {"role": "system", "content": f"You are {self.name}, a helpful assitant meant for children in elementary school. You answer the questions of children in an easy to understand and fun way. {ssml}"},
                    {"role": "user", "content": "Why is the sky blue?"},
                    {"role": "assistant", "content": '''
                    <speak>
                        <p>
                            The light from the sun goes through many many layers of air.
                            <break time="500ms"/>
                            The air is made up of tiny molecules.
                            <break time="500ms"/>
                            The sun's white light is made up of a bunch of colors, and blue is the only one that bumps into these molecules.
                            <break time="500ms"/>
                            This bumping spreads it out across the sky making it look blue.
                        </p>
                    </speak>'''},
                    {"role": "user", "content": text}
                ]
            )
            print("Responded:", completion.choices[0].message.content) 
            return "<speak>"+completion.choices[0].message.content+"</speak>"
        except Exception as e:
            self.logger.warning(e)
            self.play_sound("/home/beep/beep-assistant/audio/error.wav")
            
        finally:
            self.logger.warning('response exited')

    def text_to_wav(self, voice_name: str, text: str):
        
        try:
                     
            self.logger.info('Speech started')

            language_code = "-".join(voice_name.split("-")[:2])
            if self.SSML:
                text_input = tts.SynthesisInput(ssml=text)
            else:
                text_input = tts.SynthesisInput(text=text)
            voice_params = tts.VoiceSelectionParams(
                language_code=language_code, name=voice_name
            )
            audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=self.RATE)

            client = tts.TextToSpeechClient()
            response = client.synthesize_speech(
                input=text_input,
                voice=voice_params,
                audio_config=audio_config,
            )

            audio_data = io.BytesIO(response.audio_content) 
            # Open stream (2)
            while len(data := audio_data.read(self.CHUNK)):  # Requires Python 3.8+ for :=
                self.stream_out.write(data)
        except Exception as e:
            self.logger.warning(e)
            self.play_sound("/home/beep/beep-assistant/audio/error.wav")
            
        finally:
            self.logger.info('output closed')
    def play_sound(self, wavfile):
        
        try:
            with open(wavfile, 'rb') as f:
                data = f.read()
            self.stream_out.write(data)
        except Exception as e:
            self.logger.warning(e)
            
        finally:
            self.logger.info("sound played")



            
if __name__ == '__main__':
    print("executing")
    
    dotenv.load_dotenv()
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    os.system(f'GOOGLE_APPLICATION_CREDENTIALS={GOOGLE_APPLICATION_CREDENTIALS}')
    beep = Beep()
    beep.start()
