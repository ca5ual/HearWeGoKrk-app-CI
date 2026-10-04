"""
session.py — state of one conversation (one WebSocket connection or one REST test session).

The agent and the tools both read and write this object,
so it is the single place where "what do we know right now" lives:
language, GPS, headphones, the vehicle the user is in, the pending purchase, etc.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from mock import mock_realtime as rt

# Stage override for GPS. Set by POST /demo/gps so that every session "is" inside
# a chosen vehicle, because you can't ride a tram on stage. None = use real GPS.
# "follow" = a side number: the fake GPS then moves together with that vehicle.
DEMO_GPS: dict = {"lat": None, "lon": None, "follow": None}

# Fallback location when the phone hasn't sent GPS yet: the venue from routes.json.
_ORIGIN = rt.ROUTES["_meta"]["origin"]


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    lang: str = "pl"                     # "pl" | "en", the language the user speaks
    lat: float | None = None             # last GPS fix from the phone
    lon: float | None = None
    headphones: bool = False             # decides whether amounts may be spoken aloud
    turn: int = 0                        # incremented on every user utterance
    ai_disclosed: bool = False           # the AI disclosure was spoken (voice_ws.Conversation.speak)
    current_vehicle: str | None = None   # side number of the vehicle the user is in
    target_stop_name: str | None = None  # where the user wants to get off (for announcements)
    plan: dict | None = None             # {"legs", "start_min"} up to the last ride (ticket length)
    pending: Any = None                  # wallet.PendingAction or None
    flags: dict = field(default_factory=dict)        # small conversational flags (offers, etc.)
    history: list = field(default_factory=list)      # LLM message history (llm_agent.py)
    tool_log: list = field(default_factory=list)     # every tool call, for debugging / "log działań"
    timer_task: asyncio.Task | None = None           # confirmation timeout task (WebSocket only)

    def update_context(self, msg: dict) -> None:
        """Apply a {"type": "context", ...} message from the phone. Missing (or null) keys are left unchanged."""
        if isinstance(msg.get("lat"), (int, float)) and isinstance(msg.get("lon"), (int, float)):
            self.lat, self.lon = float(msg["lat"]), float(msg["lon"])
        if msg.get("gps") is False:  # GPS switched off on the phone -> forget the fix, fall back to the venue
            self.lat = self.lon = None
        if "headphones" in msg:
            self.headphones = bool(msg["headphones"])
        if msg.get("lang") in ("pl", "en"):
            self.lang = msg["lang"]

    @property
    def location(self) -> tuple[float, float]:
        """Best known position: demo override > phone GPS > venue."""
        if DEMO_GPS["follow"]:
            st = rt.vehicle_status(DEMO_GPS["follow"])
            if st:  # vehicle still on its trip -> stand exactly where it is
                return st["position"]["lat"], st["position"]["lon"]
        if DEMO_GPS["lat"] is not None:
            return DEMO_GPS["lat"], DEMO_GPS["lon"]
        if self.lat is not None:
            return self.lat, self.lon
        return _ORIGIN["lat"], _ORIGIN["lon"]

    def new_turn(self) -> None:
        """Call once per user utterance, BEFORE running the agent."""
        self.turn += 1

    def log_tool(self, name: str, args: dict, result: dict) -> None:
        """Append to the action log (shown in /sessions/{id}/log, useful for debugging and the pitch)."""
        self.tool_log.append({"turn": self.turn, "tool": name, "args": args, "result": result})
        del self.tool_log[:-50]  # keep the last 50 entries only

    def t(self, pl: str, en: str) -> str:
        """Pick a string in the user's language."""
        return pl if self.lang == "pl" else en
