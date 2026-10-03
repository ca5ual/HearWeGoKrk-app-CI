"""
speech.py — speech-to-text and text-to-speech.

  * transcribe(): Parakeet V3 (Person A). Until then it returns "" (use {"type": "text"}
    messages on the WebSocket to test without audio).
  * synthesize(): ElevenLabs streaming TTS. Needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID;
    without them (or on any error) it yields nothing, and the phone speaks reply_text with
    its own voice instead.

Env (see .env.example):
    ELEVENLABS_API_KEY      required for TTS
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


async def transcribe(pcm16: bytes, lang: str) -> str:
    """
    Input: raw 16 kHz mono PCM16 audio of one utterance.
    Person A: run Parakeet V3 here (NeMo or onnx-asr). Run it in a thread
    (await asyncio.to_thread(...)) so the event loop doesn't block.
    """
    return ""


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
