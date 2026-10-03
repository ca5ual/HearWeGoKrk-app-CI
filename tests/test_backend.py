"""
Run from the backend folder:  pytest -q
Covers the demo script (S1, S4, S5, S6, S7, S9, S10) and the purchase safety rules.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import tools
import wallet
from app import app
from mock import mock_realtime as rt
from session import DEMO_GPS, Session

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_demo():
    client.post("/demo/reset", json={"offset_min": 0})
    yield
    DEMO_GPS.update(lat=None, lon=None, follow=None)


def say(text, sid=None, **kw):
    r = client.post("/agent/text", json={"text": text, "session_id": sid, **kw})
    assert r.status_code == 200
    return r.json()


def test_health():
    assert client.get("/health").json()["ok"]


def test_s1_route_to_rynek():
    r = say("Jak dojadę na Rynek?")
    assert "Na miejscu o" in r["reply_text"]
    assert r["ui"][0]["component"] == "route_results"


def test_s3_hesitation():
    assert "Na miejscu o" in say("Yyy… zabierz mnie, no… na ten, Rynek chyba")["reply_text"]


def test_s4_ambiguous_rondo():
    r = say("Zawieź mnie na rondo")
    assert "Mogilskie" in r["reply_text"] and "Grzegórzeckie" in r["reply_text"]
    assert r["ui"] == []  # nothing to render until the user picks


def test_s5_high_floor_warning():
    r = say("Kiedy następna czternastka?")
    assert "wysokimi stopniami" in r["reply_text"]
    assert "niskopodłogowy" in r["reply_text"]


def test_s10_balance_privacy():
    r = say("Ile mam pieniędzy na koncie?", headphones=False)
    assert "zł" not in r["reply_text"]           # amount NOT spoken without headphones
    r2 = say("tak", sid=r["session_id"], headphones=False)
    assert "zł" in r2["reply_text"]


def _board_rz612():
    rt.reset_clock(12)  # RZ612 is on the road at minute ~12
    assert client.post("/demo/gps", json={"side_number": "RZ612"}).status_code == 200


def test_s6_s7_board_and_buy():
    _board_rz612()
    r = say("Wsiadłem")
    assert "RZ612" in r["reply_text"]
    r = say("tak", sid=r["session_id"])          # accept the "buy a ticket?" offer
    assert "Potwierdzasz?" in r["reply_text"] and "RZ612" in r["reply_text"]
    assert r["pending"]
    before = wallet.get_balance(Session())["balance_pln"]
    r = say("tak", sid=r["session_id"])          # explicit yes in a NEW turn
    assert "Kupione" in r["reply_text"]
    assert wallet.get_balance(Session())["balance_pln"] == round(before - 4.0, 2)


def test_s9_stop_cancels():
    _board_rz612()
    r = say("kup bilet")
    assert r["pending"]
    r = say("Stop! Anuluj.", sid=r["session_id"])
    assert r["pending"] is None and "Anulowałem" in r["reply_text"]


def test_confirm_rejected_in_same_turn():
    """Even if an LLM tries prepare+confirm in one turn, the backend refuses."""
    _board_rz612()
    s = Session()
    s.new_turn()
    tools.execute(s, "match_boarded_vehicle")
    prep = tools.execute(s, "prepare_ticket", {"ticket_id": "kmk_15min_n"})
    conf = tools.execute(s, "confirm_pending_action", {"pending_action_id": prep.result["pending_action_id"]})
    assert conf.result["error"] == "same_turn"


def test_ticket_needs_vehicle():
    s = Session()
    out = tools.execute(s, "prepare_ticket", {"ticket_id": "kmk_15min_n"})
    assert out.result["error"] == "missing_side_number"


def test_websocket_text_flow():
    with client.websocket_connect("/ws/voice") as ws:
        assert ws.receive_json()["type"] == "session"
        ws.receive_json()  # state idle
        ws.send_json({"type": "context", "lat": 50.0672, "lon": 19.9912, "headphones": True, "lang": "pl"})
        ws.send_json({"type": "text", "text": "Jak dojadę na AGH?"})
        types = []
        while True:
            m = ws.receive_json()
            types.append(m["type"])
            if m["type"] == "state" and m["value"] == "idle":
                break
        assert {"transcript", "ui", "reply_text"} <= set(types)


def test_tool_schemas_valid():
    names = {t["name"] for t in tools.tool_schemas_anthropic()}
    assert {"plan_route", "prepare_ticket", "confirm_pending_action", "cancel_pending_action"} <= names


def _until_idle(ws):
    msgs = []
    while True:
        m = ws.receive_json()
        msgs.append(m)
        if m["type"] == "state" and m["value"] == "idle":
            return msgs


def test_execute_never_raises():
    out = tools.execute(Session(), "plan_route", {"destination": None})
    assert out.result["error"] == "tool_failed"


def test_websocket_survives_bad_messages():
    with client.websocket_connect("/ws/voice") as ws:
        _until_idle(ws)
        ws.send_json({"type": "context", "lat": None, "lon": None, "headphones": True})
        ws.send_json({"type": "audio_chunk", "data": "not base64!!"})
        assert _until_idle(ws)[0]["type"] == "error"
        ws.send_text("{not json")
        assert _until_idle(ws)[0]["type"] == "error"
        ws.send_json({"type": "text", "text": "Jak dojadę na Rynek?"})  # connection still works
        assert any(m["type"] == "reply_text" and "Na miejscu o" in m["text"] for m in _until_idle(ws))


def test_demo_reset_clears_open_websocket():
    _board_rz612()
    with client.websocket_connect("/ws/voice") as ws:
        _until_idle(ws)
        ws.send_json({"type": "text", "text": "kup bilet"})
        assert any(m["type"] == "pending_confirmation" for m in _until_idle(ws))
        client.post("/demo/reset", json={"offset_min": 0})
        ws.send_json({"type": "text", "text": "tak"})
        replies = [m["text"] for m in _until_idle(ws) if m["type"] == "reply_text"]
        assert not any("Kupione" in r for r in replies)
    assert wallet.get_balance(Session())["balance_pln"] == 20.14


def test_extend_pending_restarts_the_window():
    """WCAG 2.2.1: "more time" resets the confirmation window but never confirms the purchase."""
    import asyncio
    import time

    import voice_ws

    async def run():
        conv = voice_ws.Conversation(ws=None)
        s = conv.session
        s.new_turn()
        _board_rz612()
        tools.execute(s, "match_boarded_vehicle")
        prep = tools.execute(s, "prepare_ticket", {"ticket_id": "kmk_15min_n"})
        pid = prep.result["pending_action_id"]
        s.pending.created_at -= 100            # almost expired
        s.pending.retries = 1
        assert not conv.extend_pending("wrong-id")
        assert conv.extend_pending(pid)
        assert time.time() - s.pending.created_at < 1 and s.pending.retries == 0
        assert s.pending is not None and conv.session.timer_task is not None
        conv.close()

    asyncio.run(run())
