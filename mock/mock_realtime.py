"""
mock_realtime.py — offline "live" transit simulator for the HearWeGoKrk demo.

Why this exists:
    Jakdojade has no public API, and live feeds can fail on venue WiFi.
    This module turns the static JSON files in this folder into data that
    *behaves* live: departures count down, vehicles move between stops,
    delays appear. Your FastAPI tools can call these functions directly,
    and later you can swap any of them for a real GTFS-RT / TTSS source
    without changing the agent's tool interface.

How time works:
    Every schedule is defined in minutes relative to SIM_START.
    Call reset_clock() right before the demo so scenario S5 (high-floor
    tram arriving first) happens on cue.
"""

import json
import math
import re
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent


def _load(name: str) -> dict:
    """Read one JSON file from this folder (UTF-8 for Polish characters)."""
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


# --- Static data, loaded once at import ---------------------------------
def reload_data() -> None:
    global _stops_file, STOPS, PLACES, _fleet, LINES, VEHICLES, ROUTES
    _stops_file = _load("stops.json")
    STOPS = {s["id"]: s for s in _stops_file["stops"]}
    PLACES = {p["id"]: p for p in _stops_file.get("places", [])}
    _fleet = _load("lines_and_vehicles.json")
    LINES = {line["id"]: line for line in _fleet["lines"]}
    VEHICLES = {v["side_number"]: v for v in _fleet["vehicles"]}
    ROUTES = _load("routes.json")


reload_data()

# Simulation epoch (unix seconds). Moved by reset_clock().
SIM_START = time.time()

# Label every answer with its source, so the agent can say how sure it is
# ("według danych na żywo" vs "według rozkładu").
DATA_SOURCE = "simulated_live"


# --- Clock helpers ------------------------------------------------------
def reset_clock(offset_min: float = 0.0) -> None:
    """Restart the simulation. offset_min > 0 jumps forward in time."""
    global SIM_START
    reload_data()
    SIM_START = time.time() - offset_min * 60


def now_min() -> float:
    """Minutes elapsed since simulation start."""
    return (time.time() - SIM_START) / 60.0


def _clock(minute: float) -> str:
    """Convert a simulation minute into a wall-clock 'HH:MM' string."""
    return time.strftime("%H:%M", time.localtime(SIM_START + minute * 60))


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in metres between two GPS points."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --- Trip model ---------------------------------------------------------
def _trips(line: dict, window_back: float, window_fwd: float):
    """
    Yield every trip of `line` whose start lies in [now-window_back, now+window_fwd].
    A trip is (k, start_min, delay_min, vehicle). k is the trip index; it may be
    negative (trips that "started before the simulation"), which keeps vehicles
    already on the road at t=0.
    """
    first, hw = line["first_departure_offset_min"], line["headway_min"]
    now = now_min()
    k = math.floor((now - window_back - first) / hw)
    while True:
        start = first + k * hw
        if start > now + window_fwd:
            break
        if start >= now - window_back:
            rot = line["vehicle_rotation"]
            delays = line.get("delay_pattern_min", [0])
            yield k, start, delays[k % len(delays)], VEHICLES[rot[k % len(rot)]]
        k += 1


def _stop_time(line: dict, stop_id: str):
    """Minutes from trip start to `stop_id`, or None if the line skips it."""
    for s in line["stops"]:
        if s["stop"] == stop_id:
            return s["t"]
    return None


def _position(line: dict, start: float, delay: float):
    """
    Linear interpolation of a vehicle between consecutive stops.
    Returns None if the trip hasn't started or has already finished.
    """
    elapsed = now_min() - start - delay
    stops = line["stops"]
    if elapsed < 0 or elapsed > stops[-1]["t"]:
        return None
    for a, b in zip(stops, stops[1:]):
        if a["t"] <= elapsed <= b["t"]:
            span = b["t"] - a["t"]
            frac = 0.0 if span == 0 else (elapsed - a["t"]) / span
            sa, sb = STOPS[a["stop"]], STOPS[b["stop"]]
            return {
                "lat": sa["lat"] + frac * (sb["lat"] - sa["lat"]),
                "lon": sa["lon"] + frac * (sb["lon"] - sa["lon"]),
                "previous_stop": a["stop"],
                "next_stop": b["stop"],
                "elapsed_min": elapsed,
            }
    return None


def _vehicle_info(v: dict) -> dict:
    """Subset of vehicle data the agent needs to speak about accessibility."""
    return {
        "side_number": v["side_number"],
        "model": v["model"],
        "low_floor": v["low_floor"],
        "audio_stop_announcements": v["audio_stop_announcements"],
        "boarding_hint_pl": v["boarding_hint_pl"],
        "boarding_hint_en": v["boarding_hint_en"],
    }


# --- Public tool functions ----------------------------------------------
def get_departures(stop_id: str, line_id: str | None = None,
                   low_floor_only: bool = False, limit: int = 3) -> list[dict]:
    """Next departures from a stop, sorted by ETA (minutes from now)."""
    out = []
    for line in LINES.values():
        if line_id and line["id"] != line_id:
            continue
        t_stop = _stop_time(line, stop_id)
        if t_stop is None or t_stop == line["stops"][-1]["t"]:
            continue  # line doesn't serve this stop, or it's the terminus
        for _, start, delay, veh in _trips(line, window_back=60, window_fwd=60):
            eta = start + delay + t_stop - now_min()
            if eta < -0.5:
                continue  # already left
            if low_floor_only and veh["low_floor"] == "none":
                continue
            out.append({
                "line_id": line["id"], "line_number": line["number"],
                "mode": line["mode"], "headsign": line["headsign"],
                "eta_min": max(0, round(eta)), "departure_time": _clock(now_min() + eta),
                "delay_min": delay, "data_source": DATA_SOURCE,
                "vehicle": _vehicle_info(veh),
            })
    return sorted(out, key=lambda d: d["eta_min"])[:limit]


def vehicle_status(side_number: str) -> dict | None:
    """Where a vehicle is right now and its ETAs to the remaining stops."""
    for line in LINES.values():
        if side_number not in line["vehicle_rotation"]:
            continue
        for _, start, delay, veh in _trips(line, window_back=60, window_fwd=0):
            if veh["side_number"] != side_number:
                continue
            pos = _position(line, start, delay)
            if pos is None:
                continue
            remaining = [
                {"stop_id": s["stop"], "name": STOPS[s["stop"]]["name"],
                 "eta_min": round(s["t"] - pos["elapsed_min"])}
                for s in line["stops"] if s["t"] >= pos["elapsed_min"]
            ]
            return {"line_id": line["id"], "line_number": line["number"],
                    "position": pos, "remaining_stops": remaining,
                    "delay_min": delay, "data_source": DATA_SOURCE,
                    "vehicle": _vehicle_info(veh)}
    return None


def find_vehicle(text: str) -> dict | None:
    """
    Side number ("numer boczny") as the user said or typed it -> vehicle, or None.
    Accepts "HG935", "hg 935", "HG-935", "h g 9 3 5" or just the digits "935", like TTSS
    (the digits are unique across the fleet; letters, when given, must match too).
    """
    up = text.upper()
    exact = re.search(r"\b([A-Z]{2})[\s-]*(\d{3})\b", up)
    if exact and exact[1] + exact[2] in VEHICLES:
        return VEHICLES[exact[1] + exact[2]]
    # Digits only (speech-to-text often garbles the letters): three digits, maybe spaced "9 3 5".
    groups = [re.sub(r"\D", "", g) for g in re.findall(r"(?<!\d)\d[\s-]?\d[\s-]?\d(?![\s-]?\d)", up)]
    hits = {s: v for s, v in VEHICLES.items() for g in groups if s[2:] == g}
    return next(iter(hits.values())) if len(hits) == 1 else None


def match_boarded_vehicle(lat: float, lon: float, line_id: str | None = None,
                          radius_m: float = 80) -> dict | None:
    """
    Auto-fill the side number: return the closest moving vehicle within radius_m
    of the user's GPS. In production, confirm the match over 2–3 consecutive GPS
    readings (user moving WITH the vehicle), not a single point.
    On stage, the demo client can simply send the vehicle's own position.
    """
    best = None
    for line in LINES.values():
        if line_id and line["id"] != line_id:
            continue
        for _, start, delay, veh in _trips(line, window_back=60, window_fwd=0):
            pos = _position(line, start, delay)
            if pos is None:
                continue
            d = _haversine_m(lat, lon, pos["lat"], pos["lon"])
            if d <= radius_m and (best is None or d < best["distance_m"]):
                best = {"distance_m": round(d), "line_id": line["id"],
                        "line_number": line["number"], "vehicle": _vehicle_info(veh)}
    return best


def resolve_destination(text: str) -> dict:
    """
    Map free text to a destination. Returns one of:
      {"status": "ok", "destination": {...}}
      {"status": "ambiguous", "options": [names]}   -> agent asks ONLY about this
      {"status": "not_found"}
    """
    q = text.lower().strip()
    dests = {d["id"]: d for d in ROUTES["destinations"]}
    # Exact alias match first, so "rondo mogilskie" wins over ambiguous "rondo".
    for d in dests.values():
        if q in d["aliases"]:
            return {"status": "ok", "destination": d}
    # Alias contained in the utterance ("na ten rynek chyba"). Longest alias first,
    # so "rondo mogilskie" wins over the ambiguous "rondo".
    pairs = sorted(((a, d) for d in dests.values() for a in d["aliases"]), key=lambda p: -len(p[0]))
    for alias, d in pairs:
        if alias in q:
            return {"status": "ok", "destination": d}
    # Only now check ambiguous words ("zawieź mnie na rondo").
    for word, ids in ROUTES["ambiguous_aliases"].items():
        if word in q:
            if len(ids) == 1:
                return {"status": "ok", "destination": dests[ids[0]]}
            return {"status": "ambiguous", "options": [dests[i]["name"] for i in ids]}
    return {"status": "not_found"}


def plan_route(destination_text: str, prefer_low_floor: bool = True) -> dict:
    """
    Fill each itinerary template with live departures and return the fastest one.
    With prefer_low_floor, vehicles with low_floor == "none" are skipped
    (the agent should still mention the skipped faster option, see scenario S5).
    """
    res = resolve_destination(destination_text)
    if res["status"] != "ok":
        return res
    dest = res["destination"]
    plans = []
    for itin in dest["itineraries"]:
        t = now_min()  # running clock while walking/riding through the legs
        legs = []
        feasible = True
        for leg in itin["legs"]:
            if leg["type"] == "walk":
                t += leg["minutes"]
                legs.append({**leg, "arrive": _clock(t)})
                continue
            line = LINES[leg["line"]]
            t_from, t_to = _stop_time(line, leg["from"]), _stop_time(line, leg["to"])
            chosen = None
            for _, start, delay, veh in _trips(line, 0, 90):
                dep = start + delay + t_from
                if dep < t:
                    continue  # we can't reach the stop in time
                if prefer_low_floor and veh["low_floor"] == "none":
                    continue
                chosen = (dep, start + delay + t_to, veh)
                break
            if chosen is None:
                feasible = False
                break
            dep, arr, veh = chosen
            legs.append({"type": "ride", "line_number": line["number"], "mode": line["mode"],
                         "headsign": line["headsign"],
                         "from": STOPS[leg["from"]]["name"], "to": STOPS[leg["to"]]["name"],
                         "departure": _clock(dep), "wait_min": round(dep - t),
                         "ride_min": round(arr - dep), "vehicle": _vehicle_info(veh)})
            t = arr
        if feasible:
            plans.append({"total_min": round(t - now_min()), "arrival": _clock(t), "legs": legs})
    if not plans:
        return {"status": "no_route", "destination": dest["name"]}
    plans.sort(key=lambda p: p["total_min"])
    q = destination_text.lower()
    if any(w in q for w in ("bus", "autobus", "autobusem", "124", "424")):
        plans.sort(key=lambda p: 0 if any(l.get("mode") == "bus" or str(l.get("line_number")) in ("124", "424") for l in p["legs"]) else 1)
    elif any(w in q for w in ("tram", "tramwaj", "tramwajem", "14", "1", "12")):
        plans.sort(key=lambda p: 0 if any(l.get("mode") == "tram" for l in p["legs"]) else 1)
    return {"status": "ok", "destination": dest["name"], "best": plans[0],
            "alternatives": plans[1:], "data_source": DATA_SOURCE}


if __name__ == "__main__":
    # Quick smoke test: python mock_realtime.py
    reset_clock()
    print(json.dumps(get_departures("tauron_arena", "T14", limit=2), ensure_ascii=False, indent=2))
    print(find_vehicle("ha gie 935"), find_vehicle("HG 935"))
    print(json.dumps(plan_route("yyy na ten rynek chyba"), ensure_ascii=False, indent=2))
    print(resolve_destination("rondo"))
