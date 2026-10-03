"""
speech.py — speech-to-text and text-to-speech. PERSON A replaces these two functions.

Until then:
  * transcribe() returns "" (use {"type": "text"} messages on the WebSocket to test without audio)
  * synthesize() yields nothing (the phone still gets reply_text and can use the OS TTS)
"""

from typing import AsyncIterator


async def transcribe(pcm16: bytes, lang: str) -> str:
    """
    Input: raw 16 kHz mono PCM16 audio of one utterance.
    Person A: run Parakeet V3 here (NeMo or onnx-asr). Run it in a thread
    (await asyncio.to_thread(...)) so the event loop doesn't block.
    """
    return ""


async def synthesize(text: str, lang: str) -> AsyncIterator[bytes]:
    """
    Person A: stream ElevenLabs audio here and `yield` each chunk (e.g. mp3_44100).
    Keep the async-generator shape so audio starts playing before synthesis finishes.
    """
    if False:  # makes this an (empty) async generator
        yield b""
