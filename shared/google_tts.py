import os
import tempfile
import ffmpeg
from google.cloud import speech_v1p1beta1 as speech
from google.oauth2 import service_account
from tools.base import instrument_io
@instrument_io(
    name="transcribe_opus_file",
    meta={"agent": "tami", "operation": "transcribe_opus_file", "tool": "transcribe_opus_file", "schema": "input_path"},
    input_fn=lambda input_path: {
        "input_path": input_path
    },
    output_fn=lambda result: result,
    redact=True,
)
def transcribe_opus_file(input_path: str) -> str:
    # Create a temporary .wav file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
        wav_path = wav_file.name

    # Convert .opus/.mp3/.ogg to .wav
    ffmpeg.input(input_path).output(
        wav_path, ac=1, ar=16000, format='wav', acodec='pcm_s16le'
    ).run(overwrite_output=True)

    try:
        with open(wav_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code="he-IL",
        )
        
        speech_creds = service_account.Credentials.from_service_account_file(
            "/etc/secrets/tami-463501-a8053925ce03.json"
        )
        client = speech.SpeechClient(credentials=speech_creds)
        response = client.recognize(config=config, audio=audio)
        return " ".join(
            result.alternatives[0].transcript for result in response.results
        )
    finally:
        os.remove(wav_path)

if __name__ == "__main__":
    print(transcribe_opus_file("heVoice1.opus"))
