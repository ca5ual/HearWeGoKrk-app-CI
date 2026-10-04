"""
Run from the backend folder:  pytest -q
Covers the demo script (S1, S4, S5, S6, S7, S9, S10) and the purchase safety rules.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import agent
import speech
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


def test_s12_will_it_be_late_names_the_data_source():
    r = say("Czy ten tramwaj na pewno się nie spóźni?")
    assert [t["name"] for t in r["tools"]] == ["get_departures"]
    assert r["reply_text"].startswith("Według danych na żywo")
    assert ".." not in r["reply_text"]


def test_departures_of_a_line_come_from_a_stop_it_serves():
    """The nearest stop (the TAURON Arena bus stop) has no trams; tram 12 leaves from Wieczysta."""
    for asked, line_id in (("Kiedy następna czternastka?", "T14"), ("Kiedy następna dwunastka?", "T12")):
        r = say(asked)
        res = r["tools"][0]["result"]
        served = {s["stop"] for s in rt.LINES[line_id]["stops"]}
        assert res["stop_id"] in served, asked
        assert res["departures"] and "Nie widzę" not in r["reply_text"], asked


def test_departures_by_mode():
    r = say("Kiedy następny autobus?")
    deps = r["tools"][0]["result"]["departures"]
    assert deps and all(d["mode"] == "bus" for d in deps)
    s = Session()
    assert tools.execute(s, "get_departures", {"line_id": "T99"}).result["error"] == "unknown_line"
    mixed = tools.execute(s, "get_departures", {"line_id": "B124", "mode": "tram"}).result
    assert mixed["departures"] and all(d["line_id"] == "B124" for d in mixed["departures"])


def test_demo_bus_de777_to_rondo_mogilskie():
    """Demo: Al. Pokoju -> Rondo Mogilskie by bus 124 DE777, 20 min ride, even without saying "autobusem".
    Tryb demo -> "Wsiadam do autobusu DE777" only moves the clock, so the route stays known:
    the ticket covers the ride to Rondo Mogilskie, not to the end of the line."""
    r = say("Jak dojadę na Rondo Mogilskie?")
    route = r["tools"][0]["result"]["best"]
    ride = next(l for l in route["legs"] if l["type"] == "ride")
    assert (ride["mode"], ride["line_number"], ride["from"], ride["to"]) == (
        "bus", "124", "TAURON Arena Kraków Al. Pokoju", "Rondo Mogilskie")
    assert ride["ride_min"] == 20 and ride["vehicle"]["side_number"] == "DE777"
    assert "Autobus 124" in r["reply_text"]

    assert client.post("/demo/clock", json={"offset_min": 11}).status_code == 200
    assert client.post("/demo/gps", json={"side_number": "DE777"}).status_code == 200
    r = say("Wsiadłem", sid=r["session_id"])
    assert "DE777" in r["reply_text"] and "normalny czy ulgowy" in r["reply_text"]  # the route sizes it
    r = say("ulgowy", sid=r["session_id"])
    prep = r["tools"][-1]["result"]
    assert prep["side_number"] == "DE777" and prep["trip_min"] < 20 and prep["covers_trip"]
    assert prep["ticket_id"] == "kmk_30min_u" and "Potwierdzasz?" in r["reply_text"]


@pytest.mark.parametrize("minute", [0, 3, 5])
def test_demo_bus_has_slack(minute):
    """Steps 2-3 of the demo take a few minutes: asking up to 5 min after the reset still gives DE777 from Al. Pokoju."""
    rt.reset_clock(minute)
    ride = rt.plan_route("rondo mogilskie")["best"]["legs"][1]
    assert (ride["vehicle"]["side_number"], ride["from"]) == ("DE777", "TAURON Arena Kraków Al. Pokoju")


def test_demo_clock_only_goes_forward():
    assert client.post("/demo/clock", json={"offset_min": 11}).status_code == 200
    assert client.post("/demo/clock", json={"offset_min": 5}).status_code == 409


def test_default_stop_has_departures():
    """Never a stop without departures: not a line's last stop, not a stop no line serves."""
    s = Session()
    for stop_id in ("salwator", "rondo_czyzynskie"):
        st = rt.STOPS[stop_id]
        s.lat, s.lon = st["lat"], st["lon"]
        res = tools.execute(s, "get_departures", {"line_id": "T1"} if stop_id == "salwator" else {}).result
        assert res["stop_id"] != stop_id and res["departures"], stop_id
    assert tools.execute(s, "get_departures", {"mode": "autobus"}).result["error"] == "bad_mode"


def test_broken_json_keeps_the_old_data(monkeypatch):
    stops = rt.STOPS
    real_load = rt._load
    monkeypatch.setattr(rt, "_load", lambda name: (_ for _ in ()).throw(ValueError("bad json"))
                        if name == "routes.json" else real_load(name))
    with pytest.raises(ValueError):
        rt.reload_data()
    assert rt.STOPS is stops


def test_mock_data_is_consistent():
    """Guards for hand-edited mock data: every route leg rides a real line in the right
    direction, and no vehicle is on two lines (it would be in two places at once)."""
    seen = {}
    for line in rt.LINES.values():
        for v in line["vehicle_rotation"]:
            assert v in rt.VEHICLES, (line["id"], v)
            assert v not in seen, f"{v} is on {seen.get(v)} and {line['id']}"
            seen[v] = line["id"]
        assert all(s["stop"] in rt.STOPS for s in line["stops"]), line["id"]
    for dest in rt.ROUTES["destinations"]:
        for it in dest["itineraries"]:
            for leg in (l for l in it["legs"] if l["type"] == "ride"):
                order = [s["stop"] for s in rt.LINES[leg["line"]]["stops"]]
                assert order.index(leg["from"]) < order.index(leg["to"]), (dest["name"], leg)


def test_late_inside_a_word_is_still_a_destination():
    r = say("Take me to the chocolate museum", lang="en")
    assert [t["name"] for t in r["tools"]] == ["plan_route"]


def test_s10_balance_privacy():
    r = say("Ile mam pieniędzy na koncie?", headphones=False)
    assert "zł" not in r["reply_text"]           # amount NOT spoken without headphones
    r2 = say("tak", sid=r["session_id"], headphones=False)
    assert "zł" in r2["reply_text"]


def _board_hg935():
    rt.reset_clock(12)  # HG935 is on the road at minute ~12
    assert client.post("/demo/gps", json={"side_number": "HG935"}).status_code == 200


def test_s6_s7_board_and_buy():
    _board_hg935()
    r = say("Wsiadłem")
    assert "HG935" in r["reply_text"] and "Dokąd jedziesz" in r["reply_text"] and "ulgowy" in r["reply_text"]
    r = say("normalny, na pół godziny", sid=r["session_id"])  # answer the "buy a ticket?" question
    assert "Potwierdzasz?" in r["reply_text"] and "HG935" in r["reply_text"]
    assert r["tools"][-1]["result"]["ticket_id"] == "kmk_30min_n"
    assert r["pending"]
    price = r["tools"][-1]["result"]["ticket"]["price_pln"]
    before = wallet.get_balance(Session())["balance_pln"]
    r = say("tak", sid=r["session_id"])          # explicit yes in a NEW turn
    assert "Kupione" in r["reply_text"]
    assert wallet.get_balance(Session())["balance_pln"] == round(before - price, 2)


def test_s9_stop_cancels():
    _board_hg935()
    r = say("kup bilet normalny na 30 minut")
    assert r["pending"]
    r = say("Stop! Anuluj.", sid=r["session_id"])
    assert r["pending"] is None and "Anulowałem" in r["reply_text"]


def test_confirm_rejected_in_same_turn():
    """Even if an LLM tries prepare+confirm in one turn, the backend refuses."""
    _board_hg935()
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


def test_side_number_said_by_user():
    """No GPS match: the user reads the side number from the sticker, the ticket uses it."""
    rt.reset_clock(12)
    r = say("Jestem w HG 935")
    assert "HG935" in r["reply_text"] and "12" in r["reply_text"]
    r = say("tak", sid=r["session_id"])          # "Kupić bilet?" -> yes, but how long and which fare
    assert "Dokąd jedziesz" in r["reply_text"] and not r["pending"]
    r = say("ulgowy", sid=r["session_id"])       # one answer at a time: only the duration is left
    assert r["reply_text"] == "Dokąd jedziesz albo na ile minut ma być bilet?" and not r["pending"]
    r = say("na 60 minut", sid=r["session_id"])
    assert "Potwierdzasz?" in r["reply_text"] and "HG935" in r["reply_text"]
    assert r["tools"][-1]["result"]["ticket_id"] == "kmk_60min_u"
    r = say("tak", sid=r["session_id"])
    assert "HG935" in r["reply_text"] and "Kupione" in r["reply_text"]


def test_side_number_forms():
    for spoken in ("HG935", "hg 935", "h g 9 3 5", "numer boczny 935"):
        assert rt.find_vehicle(spoken)["side_number"] == "HG935", spoken
    assert rt.find_vehicle("Kiedy następna 14") is None
    s = Session()
    assert tools.execute(s, "set_vehicle", {"side_number": "999"}).result["error"] == "unknown_vehicle"
    prep = tools.execute(s, "prepare_ticket", {"ticket_id": "kmk_15min_n", "side_number": "hg 935"})
    assert prep.result["side_number"] == "HG935"


# --- ticket length: valid for the whole ride ---------------------------------------
@pytest.mark.parametrize("minutes, ticket_id", [
    (None, "kmk_15min_n"),   # ride length unknown: shortest
    (12, "kmk_15min_n"),     # 12 + 3 min margin = 15
    (13, "kmk_30min_n"),
    (34, "kmk_60min_n"),     # AGH from the venue
    (58, "kmk_90min_n"),
    (200, "kmk_90min_n"),    # nothing is long enough: the longest
])
def test_pick_ticket_covers_ride_plus_margin(minutes, ticket_id):
    assert wallet.pick_ticket(minutes)["id"] == ticket_id


def test_pick_ticket_reduced_fare():
    assert wallet.pick_ticket(34, fare="reduced")["id"] == "kmk_60min_u"


def _plan_agh() -> Session:
    """AGH from the venue: walk, wait, bus 124 (the demo bus DE777, first trip after reset), walk."""
    rt.reset_clock(0)
    s = Session()
    tools.execute(s, "plan_route", {"destination": "agh"})
    return s


def test_ticket_before_boarding_follows_the_plan():
    """Not on board yet: the ride from boarding (validated in the vehicle), without the walk and the wait."""
    s = _plan_agh()
    _, ride = s.plan["legs"]
    assert wallet.trip_minutes(s, None) == ride["ride_min"]  # the final walk needs no ticket either


def test_ticket_before_boarding_al_pokoju_to_rondo_mogilskie():
    """Bus 124 Al. Pokoju -> Rondo Mogilskie is 20 min (stop t 0 -> 20): a 30-minute ticket, not 60."""
    rt.reset_clock(0)
    s = Session()
    tools.execute(s, "plan_route", {"destination": "rondo mogilskie"})
    prep = tools.execute(s, "prepare_ticket", {"side_number": "DE777", "fare": "full"}).result
    assert prep["trip_min"] == 20 and prep["ticket_id"] == "kmk_30min_n"


def test_ticket_on_the_planned_bus_uses_its_live_eta():
    s = _plan_agh()
    bus = s.plan["legs"][-1]["vehicle"]["side_number"]
    rt.reset_clock(11)  # the planned bus has just left the venue
    eta = next(x["eta_min"] for x in rt.vehicle_status(bus)["remaining_stops"] if x["name"] == "AGH / UR")
    assert wallet.trip_minutes(s, bus) == eta


def test_ticket_on_a_later_bus_is_not_too_short():
    """The user missed the planned bus and took the next 124: the planned arrival time would leave
    a few minutes, the live ETA of the bus they are on says ~23."""
    s = _plan_agh()
    rotation = rt.LINES["B124"]["vehicle_rotation"]
    later = rotation[(rotation.index(s.plan["legs"][-1]["vehicle"]["side_number"]) + 1) % len(rotation)]
    rt.reset_clock(30)
    eta = next(x["eta_min"] for x in rt.vehicle_status(later)["remaining_stops"] if x["name"] == "AGH / UR")
    s.current_vehicle = later
    prep = tools.execute(s, "prepare_ticket", {"fare": "full"}).result
    assert prep["trip_min"] == eta and prep["covers_trip"]
    assert prep["ticket"]["valid_min"] >= eta + wallet.TICKET_MARGIN_MIN


def test_ticket_covers_the_transfer():
    """On the first vehicle of a route with a transfer: this ride (live ETA) + the planned legs after
    it. Review finding: counting from the planned arrival time made this too short when the user
    took a later tram than planned (here the plan is 12 min old)."""
    rt.reset_clock(12)
    eta = next(x["eta_min"] for x in rt.vehicle_status("HG935")["remaining_stops"] if x["name"] == "Rondo Grunwaldzkie")
    s = Session(current_vehicle="HG935", plan={"start_min": 0, "legs": [
        {"type": "ride", "line_number": "12", "to": "Rondo Grunwaldzkie", "wait_min": 0, "ride_min": 0},
        {"type": "walk", "minutes": 3},
        {"type": "ride", "line_number": "1", "to": "Salwator", "wait_min": 4, "ride_min": 25},
    ]})
    assert wallet.trip_minutes(s, "HG935") == eta + 3 + 4 + 25
    prep = tools.execute(s, "prepare_ticket", {"fare": "full"}).result
    assert prep["ticket_id"] == "kmk_60min_n" and "60-minutowy" in prep["confirmation_text"]


def test_ticket_on_a_vehicle_off_the_plan_covers_the_end_of_the_line():
    """No destination, or a vehicle that isn't on the planned route."""
    s = _plan_agh()
    rt.reset_clock(12)
    end_of_line = rt.vehicle_status("HG935")["remaining_stops"][-1]["eta_min"]
    assert wallet.trip_minutes(s, "HG935") == end_of_line
    assert wallet.trip_minutes(Session(), "HG935") == end_of_line


def _prepare_on_planned_bus(ticket_id: str) -> dict:
    s = _plan_agh()
    rt.reset_clock(11)  # on the planned bus, ~32 min to AGH
    bus = s.plan["legs"][-1]["vehicle"]["side_number"]
    return tools.execute(s, "prepare_ticket", {"ticket_id": ticket_id, "side_number": bus}).result


def test_explicit_short_ticket_is_upgraded():
    """The user asks for a 15-minute ticket on a longer ride: they are offered (and must confirm) one that lasts it."""
    prep = _prepare_on_planned_bus("kmk_15min_n")
    assert prep["ticket_id"] == wallet.pick_ticket(prep["trip_min"])["id"] != "kmk_15min_n"
    assert prep["ticket"]["valid_min"] >= prep["trip_min"] + wallet.TICKET_MARGIN_MIN and prep["covers_trip"]
    assert prep["ticket"]["name_pl"] in prep["confirmation_text"]


def test_explicit_short_reduced_ticket_stays_reduced():
    prep = _prepare_on_planned_bus("kmk_15min_u")
    assert prep["ticket_id"] == wallet.pick_ticket(prep["trip_min"], "reduced")["id"] == "kmk_60min_u"


def test_explicit_long_ticket_is_kept():
    assert _prepare_on_planned_bus("kmk_90min_n")["ticket_id"] == "kmk_90min_n"


def test_rule_agent_offers_the_ticket_it_will_buy():
    """Fare and route already known: the offer names the ticket "tak" then prepares."""
    s = _plan_agh()
    s.fare = "reduced"
    rt.reset_clock(11)
    s.current_vehicle = s.plan["legs"][-1]["vehicle"]["side_number"]
    offered = wallet.pick_ticket(wallet.trip_minutes(s, s.current_vehicle), "reduced")
    assert agent._offer_ticket(s) == f"Kupić {offered['name_pl']}?"
    r = agent.rule_respond(s, "kup bilet")
    assert r.outcomes[-1].result["ticket_id"] == offered["id"]


def test_ticket_asks_for_what_the_user_did_not_say():
    """No fare and no duration / destination: ask, and nothing is pending until both are known."""
    s = Session(current_vehicle="HG935")
    r = tools.execute(s, "prepare_ticket", {}).result
    assert r["status"] == "needs_info" and r["missing"] == ["fare", "duration"] and s.pending is None
    r = tools.execute(s, "prepare_ticket", {"duration_min": 40}).result
    assert r["missing"] == ["fare"] and r["question"] == "Bilet normalny czy ulgowy?"
    r = tools.execute(s, "prepare_ticket", {"fare": "reduced"}).result
    assert r["missing"] == ["duration"] and s.pending is None
    assert tools.execute(s, "prepare_ticket", {"duration_min": 40}).result["ticket_id"] == "kmk_60min_u"  # fare remembered


@pytest.mark.parametrize("duration, ticket_id", [(15, "kmk_15min_n"), (30, "kmk_30min_n"), (40, "kmk_60min_n"), (90, "kmk_90min_n")])
def test_ticket_for_the_duration_the_user_said(duration, ticket_id):
    """"Bilet na 30 minut" is a 30-minute ticket: the margin is for rides we size, not for durations said."""
    s = Session(current_vehicle="HG935")
    assert tools.execute(s, "prepare_ticket", {"fare": "full", "duration_min": duration}).result["ticket_id"] == ticket_id


def test_rule_agent_reads_fare_and_duration():
    assert [agent._fare_of(t) for t in ("ulgowy", "mam zniżkę", "normalny", "nie mam ulgi", "bilet")] \
        == ["reduced", "reduced", "full", "full", None]
    assert [agent._duration_of(t) for t in ("30 minut", "60-minutowy", "pół godziny", "godzinę", "półtorej godziny", "kwadrans", "tak")] \
        == [30, 60, 30, 60, 90, 15, None]


def test_mock_fleet_is_ttss():
    """Vehicles marked "ttss" really are in the TTSS snapshot; the rest are "illustrative"
    (RZ105 for S5, and the bus 424 fleet). All have TTSS-style side numbers."""
    import re
    snapshot = (rt.DATA_DIR / "ttss_snapshot.json").read_text(encoding="utf-8")
    for v in rt.VEHICLES.values():
        assert re.fullmatch(r"[A-Z]{2}\d{3}", v["side_number"])
        assert v["source"] in ("ttss", "illustrative")
        assert (f'"{v["side_number"]}"' in snapshot) == (v["source"] == "ttss"), v["side_number"]
    assert rt.VEHICLES["RZ105"]["source"] == "illustrative"
    assert rt.LINES["T12"]["vehicle_rotation"][0] == "HG935"


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


def test_ticket_to_the_stop_the_user_named():
    """"Kup bilet z Alei Pokoju do Ronda Mogilskiego" on DE777, no route planned: to Rondo Mogilskie, not the end of 124."""
    rt.reset_clock(11)
    s = Session()
    prep = tools.execute(s, "prepare_ticket", {"side_number": "DE777", "get_off": "rondo mogilskie", "fare": "full"}).result
    assert prep["trip_min"] < 20 and prep["ticket_id"] == "kmk_30min_n"
    assert tools.execute(s, "prepare_ticket", {"side_number": "DE777"}).result["missing"] == ["duration"]
    err = tools.execute(s, "prepare_ticket", {"side_number": "DE777", "get_off": "Salwator"}).result
    assert err["error"] == "unknown_stop" and "Rondo Mogilskie" in err["message"]


def test_route_picked_on_screen_sizes_the_voice_ticket():
    """Expo: route tab (REST /route) Al. Pokoju -> Rondo Mogilskie, then "kup bilet" by voice on DE777.
    The plan must reach the voice session: 20 min ride -> 30 min ticket, not 60 to the end of line 124."""
    rt.reset_clock(0)
    with client.websocket_connect("/ws/voice") as ws:
        sid = _until_idle(ws)[0]["id"]
        r = client.post("/route", json={"destination": "rondo mogilskie", "session_id": sid}).json()
        assert r["best"]["legs"][1]["vehicle"]["side_number"] == "DE777"
        rt.reset_clock(11)
        assert client.post("/demo/gps", json={"side_number": "DE777"}).status_code == 200
        ws.send_json({"type": "text", "text": "kup bilet normalny"})
        spoken = [m["text"] for m in _until_idle(ws) if m["type"] == "reply_text"]
        assert "30-minutowy" in spoken[-1] and "D E 7 7 7" in spoken[-1]


def test_demo_reset_clears_open_websocket():
    _board_hg935()
    with client.websocket_connect("/ws/voice") as ws:
        _until_idle(ws)
        ws.send_json({"type": "text", "text": "kup bilet normalny na 30 minut"})
        assert any(m["type"] == "pending_confirmation" for m in _until_idle(ws))
        client.post("/demo/reset", json={"offset_min": 0})
        ws.send_json({"type": "text", "text": "tak"})
        replies = [m["text"] for m in _until_idle(ws) if m["type"] == "reply_text"]
        assert not any("Kupione" in r for r in replies)
    assert wallet.get_balance(Session())["balance_pln"] == 20.14


def test_first_voice_reply_discloses_ai():
    """AI Act: every voice user first hears "Rozmawiasz z asystentem głosowym AI." ("AI" said in English)."""
    assert speech.AI_DISCLOSURE == "Rozmawiasz z asystentem głosowym AI."
    with client.websocket_connect("/ws/voice") as ws:
        _until_idle(ws)
        ws.send_json({"type": "text", "text": "Jak dojadę na Rynek?"})
        first = next(m for m in _until_idle(ws) if m["type"] == "reply_text")
        assert first["text"].startswith(speech.AI_DISCLOSURE + " ") and "Na miejscu o" in first["text"]
        assert first["speak"].startswith(speech.AI_DISCLOSURE_SPOKEN + " ") and speech.AI_DISCLOSURE not in first["speak"]
        ws.send_json({"type": "text", "text": "Jak dojadę na Rynek?"})
        second = next(m for m in _until_idle(ws) if m["type"] == "reply_text")
        assert not second["text"].startswith(speech.AI_DISCLOSURE) and "speak" not in second
        client.post("/demo/reset", json={"offset_min": 0})  # new conversation -> disclose again
        ws.send_json({"type": "text", "text": "Jak dojadę na Rynek?"})
        again = next(m for m in _until_idle(ws) if m["type"] == "reply_text")
        assert again["text"].startswith(speech.AI_DISCLOSURE + " ")


def test_spoken_answer_closes_the_modal():
    """Voice "nie" cancels and tells the phone (modal closes); voice "tak" buys without pending_cancelled."""
    _board_hg935()
    with client.websocket_connect("/ws/voice") as ws:
        _until_idle(ws)
        ws.send_json({"type": "text", "text": "kup bilet normalny na 30 minut"})
        pid = next(m["id"] for m in _until_idle(ws) if m["type"] == "pending_confirmation")
        ws.send_json({"type": "text", "text": "nie"})
        assert {"type": "pending_cancelled", "id": pid} in _until_idle(ws)

        ws.send_json({"type": "text", "text": "kup bilet normalny na 30 minut"})
        _until_idle(ws)
        ws.send_json({"type": "text", "text": "tak"})
        msgs = _until_idle(ws)
        assert {"type": "haptic", "pattern": "confirm"} in msgs
        assert not any(m["type"] == "pending_cancelled" for m in msgs)


def test_extend_pending_restarts_the_window():
    """WCAG 2.2.1: "more time" resets the confirmation window but never confirms the purchase."""
    import asyncio
    import time

    import voice_ws

    async def run():
        conv = voice_ws.Conversation(ws=None)
        s = conv.session
        s.new_turn()
        _board_hg935()
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


def test_listening_restarts_silence_timer_but_keeps_retries():
    """Hands-free answer: the phone's "listening" restarts the silence window, but after the one
    retry, silence still cancels (the retry count is not reset, unlike extend_pending)."""
    import asyncio

    import voice_ws

    async def run():
        sent = []
        conv = voice_ws.Conversation(ws=None)

        async def fake_send(type_, **payload):
            sent.append({"type": type_, **payload})
        conv.send = fake_send
        s = conv.session
        s.new_turn()
        _board_hg935()
        tools.execute(s, "match_boarded_vehicle")
        pid = tools.execute(s, "prepare_ticket", {"ticket_id": "kmk_15min_n"}).result["pending_action_id"]
        s.pending.timeout_s = 0.05
        s.pending.retries = 1                     # the retry was already spoken
        await conv.handle_message({"type": "listening", "id": "wrong-id"})
        assert s.timer_task is None
        await conv.handle_message({"type": "listening", "id": pid})
        await asyncio.wait_for(s.timer_task, 1)
        assert s.pending is None                  # straight to cancel, no second retry
        assert {"type": "pending_cancelled", "id": pid} in sent
        conv.close()

    asyncio.run(run())


def test_long_llm_reply_does_not_eat_the_confirmation_time(monkeypatch):
    """A chatty LLM answer is replaced by the short confirmation, and the silence window and
    hard expiry only start after it has been read out."""
    import asyncio
    import time

    import agent
    import voice_ws

    async def chatty(session, text):
        tools.execute(session, "match_boarded_vehicle")
        out = tools.execute(session, "prepare_ticket", {"ticket_id": "kmk_15min_n"})
        return agent.AgentReply("Jasne! Zaraz wszystko przygotuję, to świetny wybór. " * 10, [out])

    async def run():
        sent = []
        conv = voice_ws.Conversation(ws=None)

        async def fake_send(type_, **payload):
            sent.append({"type": type_, **payload})
        conv.send = fake_send
        conv.session.ai_disclosed = True  # the disclosure is covered by test_first_reply_discloses_ai_and_the_window_counts_it
        _board_hg935()
        monkeypatch.setattr(agent, "respond", chatty)
        await conv.handle_utterance("kup bilet normalny na 30 minut")
        s = conv.session
        spoken = [m["text"] for m in sent if m["type"] == "reply_text"]
        assert spoken == [speech.spell_side_numbers(next(m for m in sent if m["type"] == "pending_confirmation")
                                                    ["data"]["confirmation_text"])]
        assert "H G 9 3 5" in spoken[0] and "Potwierdzasz?" in spoken[0]
        assert s.pending.created_at > time.time()          # window starts after the question
        assert not s.pending.hard_expired()
        conv.close()

    asyncio.run(run())


def test_first_reply_discloses_ai_and_the_window_counts_it():
    """A purchase question as the very first reply: the disclosure is read out first, so the
    silence window and hard expiry start only after both."""
    import asyncio
    import time

    import voice_ws

    async def run():
        sent = []
        conv = voice_ws.Conversation(ws=None)

        async def fake_send(type_, **payload):
            sent.append({"type": type_, **payload})
        conv.send = fake_send
        _board_hg935()
        await conv.handle_utterance("kup bilet normalny na 30 minut")
        s = conv.session
        confirmation = next(m for m in sent if m["type"] == "pending_confirmation")["data"]["confirmation_text"]
        text = next(m for m in sent if m["type"] == "reply_text")["text"]
        assert text == speech.AI_DISCLOSURE + " " + speech.spell_side_numbers(confirmation)
        assert s.ai_disclosed
        assert s.pending.created_at >= time.time() + voice_ws.speech_seconds(text) - 1
        conv.close()

    asyncio.run(run())


def test_demo_reset_during_a_turn_does_not_crash(monkeypatch):
    """Tryb demo → Reset / "Wsiadam do HG935" while the agent is still answering: the old turn is
    dropped instead of crashing on the new session ('NoneType' object has no attribute 'id')."""
    import asyncio

    import agent
    import voice_ws

    async def run():
        sent = []
        conv = voice_ws.Conversation(ws=None)

        async def fake_send(type_, **payload):
            sent.append({"type": type_, **payload})
        conv.send = fake_send
        _board_hg935()
        real = agent.respond

        async def reset_midway(session, text):
            r = await real(session, text)
            conv.reset()
            return r
        monkeypatch.setattr(agent, "respond", reset_midway)
        await conv.handle_utterance("kup bilet normalny na 30 minut")
        assert conv.session.pending is None and conv.session.timer_task is None
        assert not any(m["type"] in ("pending_confirmation", "reply_text") for m in sent)
        assert sent[-1] == {"type": "state", "value": "idle"}
        conv.close()

    asyncio.run(run())


def test_bus_124_to_rondo_mogilskie_lasts_20_minutes():
    """Bus 124 from TAURON Arena to Rondo Mogilskie lasts exactly 20 minutes."""
    rt.reset_clock(0)
    res = rt.plan_route("rondo mogilskie")
    assert res["status"] == "ok"
    # Find the B124 plan (either in best or alternatives)
    all_plans = [res["best"]] + res["alternatives"]
    b124_plans = [
        p for p in all_plans
        if any(leg.get("line_number") == "124" and leg.get("from") == "TAURON Arena Kraków Al. Pokoju" for leg in p["legs"])
    ]
    assert len(b124_plans) >= 1
    plan = b124_plans[0]
    bus_leg = next(leg for leg in plan["legs"] if leg.get("line_number") == "124")
    assert bus_leg["mode"] == "bus"
    assert bus_leg["to"] == "Rondo Mogilskie"
    assert bus_leg["ride_min"] == 20
    assert bus_leg["vehicle"]["low_floor"] == "full"


def test_route_autobusem_na_rondo_mogilskie():
    """Asking explicitly for bus to Rondo Mogilskie prioritizes bus 124."""
    rt.reset_clock(0)
    r = say("Jak dojadę autobusem na Rondo Mogilskie?")
    assert "Autobus 124" in r["reply_text"]
    assert "TAURON Arena" in r["reply_text"]
    assert "Na miejscu o" in r["reply_text"]
    assert r["ui"][0]["component"] == "route_results"


def test_bus_stops_mock_data():
    """New bus stops are properly exposed in the /stops endpoint."""
    resp = client.get("/stops")
    assert resp.status_code == 200
    stops_by_id = {s["id"]: s for s in resp.json()}
    assert "tauron_arena_krakow" in stops_by_id
    assert "brodowicza" in stops_by_id
    assert "grochowska" in stops_by_id
    assert "narzymskiego" in stops_by_id
    assert "muzeum_lotnictwa" in stops_by_id
    assert "rondo_czyzynskie" in stops_by_id
    assert "bus" in stops_by_id["tauron_arena_krakow"]["modes"]
    assert stops_by_id["tauron_arena_krakow"]["step_free_access"] is None  # not surveyed: unknown
    assert "bus" in stops_by_id["tauron_wieczysta"]["modes"]



@pytest.mark.parametrize("said, stop", [
    ("do Ronda Grunwaldzkiego", "Rondo Grunwaldzkie"), ("na pocztę główną", "Poczta Główna"),
    ("do kampusu UJ", "Kampus UJ"), ("na Czerwone Maki", "Czerwone Maki P+R"), ("Salwator", None),
    ("Jestem w HG 935, kup bilet ulgowy na 30 minut", None),
])
def test_stop_ahead_understands_polish_forms(said, stop):
    rt.reset_clock(12)
    hit = wallet.stop_ahead(rt.vehicle_status("HG935"), said)
    assert (hit and hit["name"]) == stop


def test_stop_ahead_does_not_guess_between_stops():
    rt.reset_clock(11)
    st = rt.vehicle_status("DE777")
    assert wallet.stop_ahead(st, "do Ronda") is None  # Młyńskie, Mogilskie or Grunwaldzkie
    assert wallet.stop_ahead(st, "do Dworca Głównego")["name"] == "Dworzec Główny Wschód"


def test_side_number_and_destination_in_one_sentence():
    """"Jestem w HG 935, jadę do Ronda Grunwaldzkiego, kup bilet ulgowy": 11 min + margin -> 15 min."""
    rt.reset_clock(12)
    r = say("Jestem w HG 935, jadę do Ronda Grunwaldzkiego, kup bilet ulgowy")
    prep = r["tools"][-1]["result"]
    assert prep["ticket_id"] == "kmk_15min_u" and prep["trip_min"] == 11 and r["pending"]


def test_bare_side_number_answers_the_question():
    """After "Powiedz numer boczny", just "HG 935" is the vehicle, not a destination."""
    rt.reset_clock(12)
    DEMO_GPS.update(lat=50.0, lon=19.80)  # GPS finds no vehicle
    r = say("kup bilet")
    assert "numer boczny" in r["reply_text"]
    r = say("HG 935", sid=r["session_id"])
    assert "HG935" in r["reply_text"] and "Dokąd jedziesz" in r["reply_text"]
    r = say("do Ruczaju, normalny", sid=r["session_id"])
    assert r["tools"][-1]["result"]["ticket_id"] == "kmk_30min_n"


def test_rule_agent_says_when_the_vehicle_does_not_go_there():
    rt.reset_clock(12)
    r = say("Jestem w HG 935 i jadę na Salwator, poproszę bilet normalny")
    assert r["reply_text"].startswith("Nie widzę tego przystanku") and not r["pending"]
