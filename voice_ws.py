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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import agent
import speech
import tools
import wallet
from mock import mock_realtime as rt
from session import Session

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

    async def speak(self, text: str, haptic: str | None = None) -> None:
        """Send the text, then stream TTS audio. The phone shows the text immediately."""
        await self.send("reply_text", text=text)
        if haptic:
            await self.send("haptic", pattern=haptic)
        await self.send("state", value="speaking")
        async for chunk in speech.synthesize(text, self.session.lang):
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
                self._restart_confirmation_timer()
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
        reply = await agent.respond(s, text)
        await self.emit_outcomes(reply.outcomes)
        await self.speak(reply.text)

    # --- confirmation timeout ("cisza nie jest zgodą") ------------------
    def _cancel_confirmation_timer(self) -> None:
        if self.session.timer_task and not self.session.timer_task.done():
            self.session.timer_task.cancel()
        self.session.timer_task = None

    def _restart_confirmation_timer(self) -> None:
        self._cancel_confirmation_timer()
        self.session.timer_task = asyncio.create_task(self._confirmation_timer(self.session.pending.id))

    def extend_pending(self, pending_id: str | None) -> bool:
        """Give the user a fresh confirmation window. Silence still never counts as consent."""
        p = self.session.pending
        if p is None or p.id != pending_id:
            return False
        p.created_at = time.time()
        p.retries = 0
        self._restart_confirmation_timer()
        return True

    async def _confirmation_timer(self, pending_id: str) -> None:
        s = self.session
        tpl = wallet.templates()
        try:
            for attempt in range(2):  # ask once more, then cancel
                await asyncio.sleep(s.pending.timeout_s if s.pending else 0)
                if s.pending is None or s.pending.id != pending_id:
                    return  # answered in the meantime
                if attempt == 0:
                    s.pending.retries += 1
                    await self.speak(tpl[f"silence_retry_{s.lang}"], haptic="warning")
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
        else:
            await self.send("error", message=f"unknown message type: {kind}")


# Open connections, so /demo/reset can clear them too.
ACTIVE: set[Conversation] = set()


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
                await conv.send("error", message=f"{type(e).__name__}: {e}")
                await conv.send("state", value="idle")
    except WebSocketDisconnect:
        pass
    finally:
        ACTIVE.discard(conv)
        conv.close()
