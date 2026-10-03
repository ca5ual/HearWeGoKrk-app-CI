"""
speech.py — speech-to-text and text-to-speech.

  * transcribe(): ElevenLabs Scribe speech-to-text (instead of Parakeet V3 from the README —
    no GPU or model download needed, and it accepts the AAC audio Android records).
    Needs ELEVENLABS_API_KEY with "Speech to Text" access; otherwise returns "".
  * synthesize(): ElevenLabs streaming TTS. Needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID;
    without them (or on any error) it yields nothing, and the phone speaks reply_text with
    its own voice instead.

Env (see .env.example):
    ELEVENLABS_API_KEY      required; the key needs "Text to Speech" and "Speech to Text" access
    ELEVENLABS_STT_MODEL    default scribe_v2
    ELEVENLABS_VOICE_ID     required, a voice that speaks Polish (Voice Library -> "Polish")
    ELEVENLABS_MODEL        default eleven_flash_v2_5 (~75 ms, supports Polish)
    ELEVENLABS_FORMAT       default mp3_44100_128 (the app plays mp3)
"""

import os
from typing import AsyncIterator

import httpx

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
CHUNK_BYTES = 16_000  # ~1 s of 128 kbps mp3 per WebSocket message

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:  # one pooled client: keeps the TLS connection warm between replies
        _client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _client


STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MIN_PCM_BYTES = 3200  # 100 ms of 16 kHz PCM16: ElevenLabs rejects anything shorter


def stt_configured() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def _audio_format(audio: bytes) -> tuple[str, str, str]:
    """(file_format, filename, mime) for what the phone sent: Android records AAC in an
    MP4 container (.m4a, "....ftyp" header), iOS sends raw PCM16 16 kHz mono (README 4.2)."""
    if audio[4:8] == b"ftyp":
        return "other", "speech.m4a", "audio/mp4"
    if audio[:4] == b"RIFF":
        return "other", "speech.wav", "audio/wav"
    return "pcm_s16le_16", "speech.pcm", "application/octet-stream"


async def transcribe(audio: bytes, lang: str) -> str:
    """
    ElevenLabs Scribe speech-to-text for one utterance. Returns "" when nothing was heard,
    STT isn't configured, or the request fails (the agent then asks the user to repeat).
    """
    if not stt_configured():
        return ""
    file_format, filename, mime = _audio_format(audio)
    if file_format == "pcm_s16le_16" and len(audio) < MIN_PCM_BYTES:
        return ""
    data = {
        "model_id": os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2"),
        "file_format": file_format,
        "tag_audio_events": "false",  # don't turn background noise into "(traffic)"
    }
    if lang in ("pl", "en"):
        data["language_code"] = lang  # the app's language setting; short commands misdetect otherwise
    try:
        r = await _http().post(
            STT_URL,
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            data=data,
            files={"file": (filename, audio, mime)},
        )
    except httpx.HTTPError as e:
        print(f"[stt] ElevenLabs request failed: {e!r}")
        return ""
    if r.status_code != 200:
        print(f"[stt] ElevenLabs {r.status_code}: {r.text[:300]}")
        return ""
    return (r.json().get("text") or "").strip()


def tts_configured() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID"))


async def synthesize(text: str, lang: str) -> AsyncIterator[bytes]:
    """Stream ElevenLabs audio for `text`, yielding mp3 chunks as they arrive."""
    if not text.strip() or not tts_configured():
        return
    url = TTS_URL.format(voice_id=os.environ["ELEVENLABS_VOICE_ID"])
    params = {"output_format": os.environ.get("ELEVENLABS_FORMAT", "mp3_44100_128")}
    body = {
        "text": text,
        "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
        "language_code": lang if lang in ("pl", "en") else "pl",
    }
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    buf = bytearray()
    try:
        async with _http().stream("POST", url, params=params, json=body, headers=headers) as r:
            if r.status_code != 200:
                print(f"[tts] ElevenLabs {r.status_code}: {(await r.aread())[:300]!r}")
                return  # phone falls back to its own voice
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) >= CHUNK_BYTES:
                    yield bytes(buf)
                    buf.clear()
        if buf:
            yield bytes(buf)
    except httpx.HTTPError as e:
        print(f"[tts] ElevenLabs request failed: {e!r}")
