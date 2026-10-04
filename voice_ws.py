"""
voice_ws.py — the /ws/voice endpoint (protocol in README.md, section 4.2).

One connection = one Session. Three things can make the server speak:
  1. the user (audio or text message)            -> handle_utterance()
  2. silence after a purchase question           -> _confirmation_timer()
  3. the ride itself ("wysiadasz za 2 przystanki") -> _trip_monitor()
All of them go through Conversation.speak(), which serialises sending with a lock.
"""

import asyncio
import base64
import time
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import agent
import speech
import tools
import wallet
from mock import mock_realtime as rt
from session import Session

# Rough speaking rate of the phone / ElevenLabs voice. The silence window must not run while the
# question is still being read out, so it starts only after this estimate (or earlier, when the
# phone reports "listening").
TTS_CHARS_PER_S = 12


def speech_seconds(text: str) -> float:
    return len(text) / TTS_CHARS_PER_S + 2

router = APIRouter()
TRIP_POLL_S = 10  # how often the trip monitor checks the vehicle position


class Conversation:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.session = Session()
        self.audio = bytearray()
        self.lock = asyncio.Lock()  # one sender at a time (the user loop + timers share the socket)
        self.trip_task: asyncio.Task | None = None
        self.announced: set[str] = set()  # trip announcements already spoken

    # --- sending -------------------------------------------------------
    async def send(self, type_: str, **payload) -> None:
        async with self.lock:
            await self.ws.send_json({"type": type_, **payload})

    def _intro(self) -> str:
        """What speak() puts before the next reply: the AI disclosure, once per conversation."""
        return "" if self.session.ai_disclosed else speech.AI_DISCLOSURE + " "

    async def speak(self, text: str, haptic: str | None = None) -> None:
        """Send the text, then stream TTS audio. The phone shows the text immediately.
        The first reply of a conversation starts with the AI disclosure (AI Act)."""
        text = speech.spell_side_numbers(text)  # every reply: LLM, rule brain, confirmation_text
        spoken = text
        if not self.session.ai_disclosed:
            self.session.ai_disclosed = True  # before any await: a timer can't disclose a second time
            spoken = f"{speech.disclosure_speech(self.session.lang)} {text}"
            text = f"{speech.AI_DISCLOSURE} {text}"
        # "speak": what the voice reads, when it differs from the text on screen ("AI" -> "ej-aj")
        await self.send("reply_text", text=text, **({"speak": spoken} if spoken != text else {}))
        if haptic:
            await self.send("haptic", pattern=haptic)
        await self.send("state", value="speaking")
        async for chunk in speech.synthesize(spoken, self.session.lang):
            await self.send("audio_chunk", data=base64.b64encode(chunk).decode())
        await self.send("state", value="idle")

    async def emit_outcomes(self, outcomes: list[tools.ToolOutcome]) -> None:
        """Push UI screens and the pending-confirmation signal produced by tool calls."""
        for o in outcomes:
            if o.ui:
                await self.send("ui", **o.ui)
            if o.pending:
                await self.send("pending_confirmation", id=o.pending["pending_action_id"],
                                timeout_s=o.pending["timeout_s"], data=o.pending)
            if o.name == "confirm_pending_action" and o.result.get("status") == "purchased":
                await self.send("haptic", pattern="confirm")
            if o.name == "match_boarded_vehicle" and o.result.get("matched"):
                self._start_trip_monitor()
        if self.session.pending is None:
            self._cancel_confirmation_timer()

    # --- user turns ----------------------------------------------------
    async def handle_utterance(self, text: str) -> None:
        s = self.session
        s.new_turn()
        await self.send("transcript", text=text)
        await self.send("state", value="thinking")
        before = s.pending.id if s.pending else None
        self._cancel_confirmation_timer()  # no "didn't hear you" while we work on the answer
        reply = await agent.respond(s, text)
        if s is not self.session:
            # POST /demo/reset (Tryb demo) replaced the session while this turn was running:
            # its answer belongs to the old session, don't speak it or touch the new one.
            await self.send("state", value="idle")
            return
        await self.emit_outcomes(reply.outcomes)
        new = next((o.pending for o in reply.outcomes if o.pending), None)
        if new and s.pending is not None and s.pending.id == new["pending_action_id"]:
            # Speak only the confirmation (ticket, price, vehicle, "Potwierdzasz?"): a long LLM
            # answer would eat the time the user has to say "tak".
            reply.text = new["confirmation_text"]
            grace = speech_seconds(self._intro() + reply.text)  # the AI disclosure is read out first
            s.pending.created_at = time.time() + grace  # hard expiry counts from after the question
            self._restart_confirmation_timer(grace)
        # A spoken "nie" / "stop" cancelled the purchase: close the confirmation modal on the phone.
        bought = any(o.name == "confirm_pending_action" and o.result.get("status") == "purchased"
                     for o in reply.outcomes)
        if before and (s.pending is None or s.pending.id != before) and not bought:
            await self.send("pending_cancelled", id=before)
        elif before and s.pending is not None and s.pending.id == before:
            # Unclear answer: a fresh window for the next one, after this reply is read out.
            self._restart_confirmation_timer(speech_seconds(self._intro() + reply.text))
        await self.speak(reply.text)

    # --- confirmation timeout ("cisza nie jest zgodą") ------------------
    def _cancel_confirmation_timer(self) -> None:
        if self.session.timer_task and not self.session.timer_task.done():
            self.session.timer_task.cancel()
        self.session.timer_task = None

    def _restart_confirmation_timer(self, grace_s: float = 0) -> None:
        """grace_s: time the phone still needs to read the question out before silence counts."""
        self._cancel_confirmation_timer()
        if self.session.pending is None:
            return  # nothing to confirm (e.g. cancelled or reset in the meantime)
        self.session.timer_task = asyncio.create_task(self._confirmation_timer(self.session.pending.id, grace_s))

    def extend_pending(self, pending_id: str | None) -> bool:
        """Give the user a fresh confirmation window. Silence still never counts as consent."""
        p = self.session.pending
        if p is None or p.id != pending_id:
            return False
        p.created_at = time.time()
        p.retries = 0
        self._restart_confirmation_timer()
        return True

    async def _confirmation_timer(self, pending_id: str, grace_s: float = 0) -> None:
        s = self.session
        tpl = wallet.templates()
        try:
            # Ask once more, then cancel. Restarts ("listening") keep the retry count.
            for attempt in range(s.pending.retries if s.pending else 0, 2):
                await asyncio.sleep((s.pending.timeout_s if s.pending else 0) + grace_s)
                grace_s = 0
                if s.pending is None or s.pending.id != pending_id:
                    return  # answered in the meantime
                if attempt == 0:
                    s.pending.retries += 1
                    retry = tpl[f"silence_retry_{s.lang}"]
                    s.pending.created_at = time.time() + speech_seconds(retry)
                    await self.speak(retry, haptic="warning")
                    grace_s = speech_seconds(retry)
                else:
                    wallet.cancel(s)
                    s.log_tool("auto_cancel_on_silence", {}, {"status": "cancelled"})
                    await self.send("pending_cancelled", id=pending_id)
                    await self.speak(tpl[f"silence_cancel_{s.lang}"])
        except asyncio.CancelledError:
            pass

    # --- trip announcements ---------------------------------------------
    def _start_trip_monitor(self) -> None:
        if self.trip_task and not self.trip_task.done():
            self.trip_task.cancel()
        self.announced.clear()
        self.trip_task = asyncio.create_task(self._trip_monitor())

    async def _trip_monitor(self) -> None:
        s = self.session
        try:
            while s.current_vehicle:
                st = rt.vehicle_status(s.current_vehicle)
                if st is None:
                    return  # trip ended
                await self.send("ui", component="trip_live", data=st)
                names = [x["name"] for x in st["remaining_stops"]]
                if s.target_stop_name in names:
                    idx = names.index(s.target_stop_name)  # 0 = the next stop is ours
                    if idx == 1 and "two" not in self.announced:
                        self.announced.add("two")
                        await self.speak(s.t(f"Za dwa przystanki wysiadasz, na przystanku {s.target_stop_name}.",
                                             f"Two more stops, you get off at {s.target_stop_name}."))
                    elif idx == 0 and "next" not in self.announced:
                        self.announced.add("next")
                        await self.speak(s.t(f"Następny przystanek {s.target_stop_name}. Przygotuj się do wyjścia.",
                                             f"Next stop {s.target_stop_name}. Get ready to get off."),
                                         haptic="arrived")
                await asyncio.sleep(TRIP_POLL_S)
        except asyncio.CancelledError:
            pass

    def close(self) -> None:
        self._cancel_confirmation_timer()
        if self.trip_task:
            self.trip_task.cancel()

    def reset(self) -> None:
        """POST /demo/reset: drop the conversation state, keep the connection and the phone's context."""
        self.close()
        old = self.session
        self.session = Session(id=old.id, lang=old.lang, lat=old.lat, lon=old.lon, headphones=old.headphones)
        self.audio = bytearray()
        self.announced.clear()

    # --- incoming messages ---------------------------------------------
    async def handle_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "context":
            self.session.update_context(msg)
        elif kind == "audio_chunk":
            self.audio.extend(base64.b64decode(msg["data"]))
        elif kind == "end_of_speech":
            pcm, self.audio = bytes(self.audio), bytearray()
            await self.send("state", value="thinking")
            text = await speech.transcribe(pcm, self.session.lang)
            await self.handle_utterance(text)
        elif kind == "text":  # typed input: testing, and an accessible alternative to speech
            await self.handle_utterance(msg.get("text", ""))
        elif kind == "stop":  # hardware/emergency stop button on the phone
            await self.handle_utterance("stop")
        elif kind == "extend_pending":  # "more time" on the confirmation modal (WCAG 2.2.1)
            self.extend_pending(msg.get("id"))
        elif kind == "listening":  # the phone finished reading the question and opened the mic
            p = self.session.pending
            if p is not None and p.id == msg.get("id"):
                p.created_at = time.time()  # the answer window (and hard expiry) counts from now
                self._restart_confirmation_timer()
        else:
            await self.send("error", message=f"unknown message type: {kind}")


# Open connections, so /demo/reset can clear them too.
ACTIVE: set[Conversation] = set()


def session_by_id(session_id: str | None) -> Session | None:
    """The voice session of an open connection (a route picked on screen must reach it)."""
    return next((c.session for c in ACTIVE if session_id and c.session.id == session_id), None)


@router.websocket("/ws/voice")
async def voice(ws: WebSocket):
    await ws.accept()
    conv = Conversation(ws)
    ACTIVE.add(conv)
    await conv.send("session", id=conv.session.id)
    await conv.send("state", value="idle")
    try:
        while True:
            try:
                await conv.handle_message(await ws.receive_json())
            except WebSocketDisconnect:
                raise
            except Exception as e:  # one bad message must not kill the connection
                print(f"[ws] bad message: {e!r}")
                traceback.print_exc()  # where it happened, in the uvicorn terminal
                await conv.send("error", message=f"{type(e).__name__}: {e}")
                await conv.send("state", value="idle")
    except WebSocketDisconnect:
        pass
    finally:
        ACTIVE.discard(conv)
        conv.close()
