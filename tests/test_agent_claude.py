"""
Claude agent + ElevenLabs TTS, tested offline: a scripted fake Anthropic client and a mocked
ElevenLabs endpoint. No API keys needed, nothing is billed.  Run: pytest -q
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic
import httpx2  # the Anthropic SDK 1.x HTTP library
import httpx
import pytest
from fastapi.testclient import TestClient

import agent
import llm_agent
import speech
import wallet
from app import app
from mock import mock_realtime as rt
from session import DEMO_GPS, Session

client = TestClient(app)


# --- fakes -----------------------------------------------------------------------
def text(t):
    return NS(type="text", text=t)


def call(name, id_, **inp):
    return NS(type="tool_use", name=name, id=id_, input=inp)


def resp(*content, stop=None):
    stop = stop or ("tool_use" if any(b.type == "tool_use" for b in content) else "end_turn")
    return NS(content=list(content), stop_reason=stop)


class FakeClaude:
    """Returns scripted responses in order; an Exception in the script is raised instead."""

    def __init__(self, *script):
        self.script = list(script)
        self.requests = []
        self.beta = NS(messages=NS(create=self.create))

    async def create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def api_down():
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    client.post("/demo/reset", json={"offset_min": 0})
    monkeypatch.setattr(agent, "USE_LLM", True)
    yield
    DEMO_GPS.update(lat=None, lon=None, follow=None)
    llm_agent._client = None


def run(session, text_):
    session.new_turn()
    return asyncio.run(agent.respond(session, text_))


def tool_results(req):
    """tool_result blocks of the last user message in a recorded request."""
    return req["messages"][-1]["content"]


# --- Claude agent ---------------------------------------------------------------------
def test_route_turn_and_request_shape():
    fake = FakeClaude(
        resp(call("plan_route", "t1", destination="rynek")),
        resp(text("Tramwaj 1 za 5 minut, niskopodłogowy.")),
    )
    llm_agent._client = fake
    s = Session(headphones=True)
    r = run(s, "Jak dojadę na Rynek?")

    assert r.text == "Tramwaj 1 za 5 minut, niskopodłogowy."
    assert r.outcomes[0].ui["component"] == "route_results"
    req = fake.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["output_config"] == {"effort": "low"}
    assert {t["name"] for t in req["tools"]} >= {"plan_route", "prepare_ticket", "confirm_pending_action"}
    first_user = req["messages"][0]["content"]
    assert first_user.startswith("[kontekst:") and "słuchawki: tak" in first_user
    assert first_user.endswith("Jak dojadę na Rynek?")
    result = json.loads(tool_results(fake.requests[1])[0]["content"])
    assert result["status"] == "ok" and tool_results(fake.requests[1])[0]["tool_use_id"] == "t1"
    # history: user, assistant(tool_use), user(tool_result), assistant(text)
    assert [m["role"] for m in s.history] == ["user", "assistant", "user", "assistant"]


def _board_rz612():
    rt.reset_clock(12)
    assert client.post("/demo/gps", json={"side_number": "HG935"}).status_code == 200


def test_buy_ticket_over_two_turns():
    _board_rz612()
    before = wallet.get_balance(Session())["balance_pln"]
    fake = FakeClaude(
        # turn 1: two parallel calls -> both results come back in ONE user message
        resp(call("match_boarded_vehicle", "a"), call("prepare_ticket", "b", ticket_id="kmk_15min_n")),
        resp(text("Kupuję bilet 15-minutowy normalny... Potwierdzasz?")),
        # turn 2: explicit yes
        resp(call("confirm_pending_action", "c")),
        resp(text("Kupione.")),
    )
    llm_agent._client = fake
    s = Session(headphones=True)

    r1 = run(s, "Kup bilet")
    assert s.pending is not None and s.current_vehicle == "HG935"
    ticket = s.pending.params["ticket"]  # 15 min is too short for HG935's ride: upgraded
    assert ticket["id"] == "kmk_30min_n"
    assert [b["tool_use_id"] for b in tool_results(fake.requests[1])] == ["a", "b"]
    assert wallet.get_balance(Session())["balance_pln"] == before  # nothing paid yet
    assert any(o.pending for o in r1.outcomes)

    r2 = run(s, "tak")
    assert r2.text == "Kupione." and s.pending is None
    assert wallet.get_balance(Session())["balance_pln"] == round(before - ticket["price_pln"], 2)
    assert "oczekujący zakup: pa_" in fake.requests[2]["messages"][-1]["content"]


def test_confirm_in_same_turn_is_refused():
    _board_rz612()
    before = wallet.get_balance(Session())["balance_pln"]
    fake = FakeClaude(
        resp(call("prepare_ticket", "p", ticket_id="kmk_15min_n")),
        resp(call("confirm_pending_action", "c")),  # model tries to skip the user's answer
        resp(text("Potwierdzasz?")),
    )
    llm_agent._client = fake
    s = Session(headphones=True)
    s.current_vehicle = "HG935"
    run(s, "kup bilet")
    res = tool_results(fake.requests[2])[0]
    assert res["is_error"] and json.loads(res["content"])["error"] == "same_turn"
    assert wallet.get_balance(Session())["balance_pln"] == before


def test_api_down_before_tools_falls_back_to_rules():
    llm_agent._client = FakeClaude(api_down())
    r = run(Session(), "Jak dojadę na Rynek?")
    assert "Na miejscu o" in r.text  # rule brain answered


def test_api_down_after_purchase_does_not_redo_turn():
    _board_rz612()
    s = Session(headphones=True)
    s.current_vehicle = "HG935"
    s.new_turn()
    wallet.prepare_ticket(s, "kmk_15min_n")
    llm_agent._client = FakeClaude(resp(call("confirm_pending_action", "c")), api_down())
    r = run(s, "tak")
    assert r.text.startswith("Kupione")
    assert [o.name for o in r.outcomes] == ["confirm_pending_action"]  # rule brain did not run


def test_refusal_is_handled():
    llm_agent._client = FakeClaude(resp(text(""), stop="refusal"))
    r = run(Session(), "...")
    assert r.text.startswith("Przepraszam")


# --- ElevenLabs TTS ---------------------------------------------------------------------
def _mock_elevenlabs(monkeypatch, handler):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice123")
    monkeypatch.setattr(speech, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def _collect(gen):
    return [c async for c in gen]


def test_tts_streams_mp3(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen.update(url=str(req.url), key=req.headers["xi-api-key"], body=json.loads(req.content))
        return httpx.Response(200, content=b"\xff\xfb" + b"a" * 40_000, headers={"content-type": "audio/mpeg"})

    _mock_elevenlabs(monkeypatch, handler)
    chunks = asyncio.run(_collect(speech.synthesize("Tramwaj 14 za 6 minut.", "pl")))
    assert b"".join(chunks).startswith(b"\xff\xfb") and sum(map(len, chunks)) == 40_002
    assert seen["url"].startswith("https://api.elevenlabs.io/v1/text-to-speech/voice123/stream")
    assert "output_format=mp3_44100_128" in seen["url"] and seen["key"] == "test-key"
    assert seen["body"] == {"text": "Tramwaj 14 za 6 minut.", "model_id": "eleven_flash_v2_5", "language_code": "pl"}


def test_tts_error_or_missing_config_yields_nothing(monkeypatch):
    _mock_elevenlabs(monkeypatch, lambda req: httpx.Response(401, json={"detail": "bad key"}))
    assert asyncio.run(_collect(speech.synthesize("Cześć", "pl"))) == []
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert asyncio.run(_collect(speech.synthesize("Cześć", "pl"))) == []


def test_websocket_sends_tts_audio(monkeypatch):
    monkeypatch.setattr(agent, "USE_LLM", False)
    _mock_elevenlabs(monkeypatch, lambda req: httpx.Response(200, content=b"mp3" * 10))
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json(), ws.receive_json()
        ws.send_json({"type": "text", "text": "Jak dojadę na Rynek?"})
        msgs = []
        while not (msgs and msgs[-1] == {"type": "state", "value": "idle"}):
            msgs.append(ws.receive_json())
    types = [m["type"] for m in msgs]
    assert types.index("reply_text") < types.index("audio_chunk")
    assert any(m["type"] == "audio_chunk" and m["data"] for m in msgs)


def test_real_sdk_request_and_history_serialization():
    """The real anthropic client on a mocked transport: request JSON is valid and the
    assistant content (SDK objects) round-trips into the next request."""
    bodies, replies = [], [
        {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
         "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                     {"type": "tool_use", "id": "toolu_1", "name": "plan_route", "input": {"destination": "agh"}}],
         "stop_reason": "tool_use", "stop_sequence": None,
         "usage": {"input_tokens": 10, "output_tokens": 5}},
        {"id": "msg_2", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
         "content": [{"type": "text", "text": "Tramwaj 14."}],
         "stop_reason": "end_turn", "stop_sequence": None,
         "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]

    def handler(req):
        bodies.append((dict(req.headers), json.loads(req.content)))
        return httpx2.Response(200, json=replies[len(bodies) - 1])

    llm_agent._client = anthropic.AsyncAnthropic(
        api_key="test", http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)))
    r = run(Session(), "How do I get to AGH?")

    assert r.text == "Tramwaj 14."
    headers, first = bodies[0]
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]
    assert first["fallbacks"] == "default" and first["output_config"] == {"effort": "low"}
    assert first["cache_control"] == {"type": "ephemeral"}
    second = bodies[1][1]["messages"]
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}  # echoed unchanged
    assert second[2]["content"][0]["type"] == "tool_result" and second[2]["content"][0]["tool_use_id"] == "toolu_1"


def test_empty_utterance_skips_claude():
    fake = FakeClaude()  # any request would fail: the script is empty
    llm_agent._client = fake
    r = run(Session(), "   ")
    assert "Nie usłyszałem" in r.text and fake.requests == []


# --- ElevenLabs STT ---------------------------------------------------------------------
def _stt_handler(seen, reply_text="Jak dojadę na Rynek?", status=200):
    def handler(req: httpx.Request):
        body = req.content.decode("latin-1")
        seen.append({"url": str(req.url), "key": req.headers["xi-api-key"], "body": body})
        if status != 200:
            return httpx.Response(status, json={"detail": "nope"})
        return httpx.Response(200, json={"text": f" {reply_text} ", "language_code": "pol"})
    return handler


def _field(body, name):
    """Value of a multipart form field."""
    part = body.split(f'name="{name}"', 1)[1]
    return part.split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0]


def test_stt_android_m4a(monkeypatch):
    seen = []
    _mock_elevenlabs(monkeypatch, _stt_handler(seen))
    m4a = b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000
    assert asyncio.run(speech.transcribe(m4a, "pl")) == "Jak dojadę na Rynek?"
    b = seen[0]["body"]
    assert seen[0]["url"] == "https://api.elevenlabs.io/v1/speech-to-text" and seen[0]["key"] == "test-key"
    assert _field(b, "model_id") == "scribe_v2" and _field(b, "file_format") == "other"
    assert _field(b, "language_code") == "pl" and 'filename="speech.m4a"' in b


def test_stt_ios_raw_pcm(monkeypatch):
    seen = []
    _mock_elevenlabs(monkeypatch, _stt_handler(seen, "How do I get to AGH?"))
    assert asyncio.run(speech.transcribe(b"\x01\x00" * 8000, "en")) == "How do I get to AGH?"
    assert _field(seen[0]["body"], "file_format") == "pcm_s16le_16"
    assert _field(seen[0]["body"], "language_code") == "en"


def test_stt_too_short_error_or_unconfigured_returns_empty(monkeypatch):
    seen = []
    _mock_elevenlabs(monkeypatch, _stt_handler(seen, status=401))
    assert asyncio.run(speech.transcribe(b"\x00" * 100, "pl")) == "" and seen == []  # < 100 ms: no request
    assert asyncio.run(speech.transcribe(b"\x00" * 9000, "pl")) == ""                 # 401 -> ""
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert asyncio.run(speech.transcribe(b"\x00" * 9000, "pl")) == ""


def test_websocket_voice_turn_end_to_end(monkeypatch):
    """audio_chunk + end_of_speech -> STT -> agent -> reply + TTS audio."""
    monkeypatch.setattr(agent, "USE_LLM", False)

    def handler(req: httpx.Request):
        if req.url.path == "/v1/speech-to-text":
            return httpx.Response(200, json={"text": "Jak dojadę na Rynek?"})
        return httpx.Response(200, content=b"mp3" * 100)

    _mock_elevenlabs(monkeypatch, handler)
    import base64
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json(), ws.receive_json()
        audio = b"\x00\x00\x00\x18ftypmp42" + b"a" * 4000
        ws.send_json({"type": "audio_chunk", "data": base64.b64encode(audio).decode()})
        ws.send_json({"type": "end_of_speech"})
        msgs = []
        while not (len(msgs) > 2 and msgs[-1] == {"type": "state", "value": "idle"}):
            msgs.append(ws.receive_json())
    assert {"type": "transcript", "text": "Jak dojadę na Rynek?"} in msgs
    assert any(m["type"] == "reply_text" and "Na miejscu o" in m["text"] for m in msgs)
    assert any(m["type"] == "audio_chunk" for m in msgs)


def test_side_numbers_are_spelled_out():
    llm_agent._client = FakeClaude(resp(text("Jesteś w HG935, a następny to HG 936. Bilet 15 minut.")))
    r = run(Session(), "w czym jestem?")
    assert r.text == "Jesteś w H G 9 3 5, a następny to H G 9 3 6. Bilet 15 minut."
