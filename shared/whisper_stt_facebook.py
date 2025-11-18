import os
import tempfile
import requests
from typing import Optional
from dotenv import load_dotenv
from context.primitives.media import MediaInfo
from shared.google_tts import transcribe_opus_file
from tools.base import instrument_io
load_dotenv(".venv/.env")

FB_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

def get_facebook_media_url(media_id: str, access_token: str) -> str:
    url = f"https://graph.facebook.com/v16.0/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["url"]

def download_media_to_tempfile(media_url: str, access_token: str, mime_type: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(media_url, headers=headers, stream=True)
    response.raise_for_status()

    # Normalize mime type
    mime_type = mime_type.split(";")[0].strip().lower()

    suffix = {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm"
    }.get(mime_type, ".mp3")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        for chunk in response.iter_content(chunk_size=8192):
            tmp_file.write(chunk)
        return tmp_file.name

@instrument_io(
    name="transcribe_facebook_audio",
    meta={"agent": "tami", "operation": "transcribe_facebook_audio", "tool": "transcribe_facebook_audio", "schema": "MediaInfo.v1"},
    input_fn=lambda media_info: {
        "media_info": (media_info.model_dump() if hasattr(media_info, "model_dump")
                  else media_info.dict() if hasattr(media_info, "dict")
                  else media_info)
    },
    output_fn=lambda result: result,
    redact=True,
)
def transcribe_facebook_audio(media_info: MediaInfo) -> str:
    if not media_info.media_id:
        raise ValueError("MediaInfo must have a media_id")

    media_url = get_facebook_media_url(media_info.media_id, FB_TOKEN)
    file_path = download_media_to_tempfile(media_url, FB_TOKEN, media_info.mime_type)
    try:
        return transcribe_opus_file(file_path)
    finally:
        os.remove(file_path)


if __name__ == "__main__":

    media = MediaInfo(
        media_id="1052689170159365",
        mime_type="audio/ogg; codecs=opus",
        url=""
    )

    result = transcribe_facebook_audio(media)
    print("Transcription:", result)
