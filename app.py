"""
app.py — HearWeGoKrk backend entry point.

Run (from this folder):
    pip install -r requirements.txt
    uvicorn app:app --reload --host 0.0.0.0 --port 8000
Then open http://localhost:8000/docs for the interactive API.
The phone must be on the same network and use ws://<laptop-ip>:8000/ws/voice.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import agent
import tools
import voice_ws
import wallet
from mock import mock_realtime as rt
from session import DEMO_GPS, Session
from voice_ws import router as voice_router

app = FastAPI(title="HearWeGoKrk backend", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(voice_router)

# Sessions for the REST /agent/text endpoint (WebSocket sessions live in their connection).
REST_SESSIONS: dict[str, Session] = {}


# --- request bodies ------------------------------------------------------
class RouteReq(BaseModel):
    destination: str
    prefer_low_floor: bool | None = None


class AgentTextReq(BaseModel):
    text: str
    session_id: str | None = None
    lang: str = "pl"
    headphones: bool = False


class ResetReq(BaseModel):
    offset_min: float = 0


class GpsReq(BaseModel):
    side_number: str | None = None  # put the "user" inside this vehicle
    lat: float | None = None        # ...or at an explicit point
    lon: float | None = None


# --- basics --------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "sim_minute": round(rt.now_min(), 1), "llm": agent.USE_LLM, "demo_gps": DEMO_GPS}


@app.get("/stops")
def stops():
    return list(rt.STOPS.values())


@app.get("/stops/{stop_id}/departures")
def departures(stop_id: str, line_id: str | None = None, low_floor_only: bool = False, limit: int = 5):
    if stop_id not in rt.STOPS:
        raise HTTPException(404, "unknown stop")
    return rt.get_departures(stop_id, line_id=line_id, low_floor_only=low_floor_only, limit=limit)


@app.get("/vehicles/{side_number}")
def vehicle(side_number: str):
    st = rt.vehicle_status(side_number)
    if st is None:
        raise HTTPException(404, "vehicle not on a trip right now")
    return st


@app.post("/route")
def route(req: RouteReq):
    return tools.execute(Session(), "plan_route", req.model_dump(exclude_none=True)).result


@app.get("/wallet")
def get_wallet():
    return wallet.get_balance(Session(headphones=True))


@app.get("/tickets/catalog")
def ticket_catalog():
    return wallet.catalog()


@app.get("/tools/schemas")
def schemas(fmt: str = "anthropic"):
    """For Person A: the tool definitions to pass to the LLM."""
    return tools.tool_schemas_openai() if fmt == "openai" else tools.tool_schemas_anthropic()


# --- text agent over REST (testing without the phone) ----------------------
@app.post("/agent/text")
async def agent_text(req: AgentTextReq):
    s = REST_SESSIONS.get(req.session_id or "") or Session(lang=req.lang)
    REST_SESSIONS[s.id] = s
    s.headphones = req.headphones
    s.new_turn()
    reply = await agent.respond(s, req.text)
    return {
        "session_id": s.id,
        "reply_text": reply.text,
        "ui": [o.ui for o in reply.outcomes if o.ui],
        "tools": [{"name": o.name, "args": o.args, "result": o.result} for o in reply.outcomes],
        "pending": s.pending.id if s.pending else None,
    }


@app.get("/sessions/{session_id}/log")
def session_log(session_id: str):
    s = REST_SESSIONS.get(session_id)
    if s is None:
        raise HTTPException(404, "unknown session")
    return s.tool_log


# --- demo controls ---------------------------------------------------------
@app.post("/demo/reset")
def demo_reset(req: ResetReq = ResetReq()):
    """Run right before going on stage: restarts the clock, wallet and GPS override."""
    rt.reset_clock(req.offset_min)
    wallet.reset()
    DEMO_GPS.update(lat=None, lon=None, follow=None)
    REST_SESSIONS.clear()
    for conv in list(voice_ws.ACTIVE):
        conv.reset()
    return {"ok": True, "sim_minute": round(rt.now_min(), 1)}


@app.post("/demo/gps")
def demo_gps(req: GpsReq):
    """Fake the user's GPS for every session: inside a running vehicle, or at a fixed point."""
    if req.side_number:
        st = rt.vehicle_status(req.side_number)
        if st is None:
            raise HTTPException(409, f"{req.side_number} is not on a trip right now — try /demo/reset with an offset")
        DEMO_GPS.update(lat=st["position"]["lat"], lon=st["position"]["lon"], follow=req.side_number)
    elif req.lat is not None and req.lon is not None:
        DEMO_GPS.update(lat=req.lat, lon=req.lon, follow=None)
    else:
        raise HTTPException(400, "give side_number or lat+lon")
    return {"ok": True, "demo_gps": DEMO_GPS}


@app.delete("/demo/gps")
def demo_gps_clear():
    DEMO_GPS.update(lat=None, lon=None, follow=None)
    return {"ok": True}
