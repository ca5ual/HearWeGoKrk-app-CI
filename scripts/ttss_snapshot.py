"""
ttss_snapshot.py — build the mock fleet and stops from Kraków's live TTSS feed (https://beta.ttss.pl).

    .venv/bin/python scripts/ttss_snapshot.py            # fetch api.ttss.pl, rewrite the mock files
    .venv/bin/python scripts/ttss_snapshot.py --offline  # rebuild from the saved mock/ttss_snapshot.json

Writes:
    mock/ttss_snapshot.json       raw extract: vehicles seen on our lines + one real trip per line
    mock/stops.json               real stop names and platform coordinates (accessibility flags kept)
    mock/lines_and_vehicles.json  real stop order + travel times, real side numbers ("numer boczny"),
                                  models, low-floor and air-con, exactly as TTSS shows them

What stays curated (TTSS has no such data): headways, delay patterns, boarding hints, the demo
vehicle order (HG935 first on line 12) and one illustrative high-floor tram for scenario S5.
Run it while trams are running (roughly 5:00–23:00); lines with no live vehicle keep their
previous snapshot.
"""

import json
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "mock"
API = "https://api.ttss.pl"   # the backend of beta.ttss.pl (see its map.js)

# One direction per line: from the venue towards the city. Trip stops are cut at `board`.
LINES = [
    {"id": "T1", "type": "t", "number": "1", "headsign": "Salwator", "board": "TAURON Arena Kraków Al. Pokoju",
     "first_departure_offset_min": 5, "headway_min": 10, "delay_pattern_min": [0, 2, 0, 1]},
    {"id": "T12", "type": "t", "number": "12", "headsign": "Czerwone Maki P+R", "board": "TAURON Arena Kraków Wieczysta",
     "first_departure_offset_min": 4, "headway_min": 10, "delay_pattern_min": [0, 1, 0],
     "first_vehicle": "HG935"},  # demo: on board at minute ~12 (Ustawienia → Tryb demo)
    {"id": "T14", "type": "t", "number": "14", "headsign": "Dworzec Towarowy", "board": "TAURON Arena Kraków Al. Pokoju",
     "first_departure_offset_min": 3, "headway_min": 8, "delay_pattern_min": [3, 0, 1],
     "first_vehicle": "RZ105"},  # S5: the first 14 is high-floor and 3 min late
    {"id": "B124", "type": "b", "number": "124", "headsign": "Os. Podwawelskie", "board": "TAURON Arena Kraków Al. Pokoju",
     "first_departure_offset_min": 6, "headway_min": 15, "delay_pattern_min": [0, 4],
     "skip": ["TAURON Arena Kraków", "TAURON Arena Kraków Wieczysta"]},  # loop around the arena
]
MAX_ROTATION = 6

# Not in TTSS today (Kraków retired its last fully high-floor trams), kept only so scenario S5
# ("old tram with high steps") can still be shown. Marked "source": "illustrative".
ILLUSTRATIVE = [
    {"num": "RZ105", "type": "105Na", "low": 0, "ac": 0, "mode": "tram"},
]

STOP_IDS = {"TAURON Arena Kraków Al. Pokoju": "tauron_arena", "TAURON Arena Kraków Wieczysta": "tauron_wieczysta"}

MODELS = {
    "2014N": "PESA 2014N Krakowiak",
    "Stadler Tango": "Stadler Tango Lajkonik",
    "Stadler Tango II": "Stadler Tango Lajkonik II",
    "105Na": "Konstal 105Na",
}

HINTS = {  # low-floor value in TTSS: 0 none, 1 partial, 2 full
    ("tram", 2): ("Niska podłoga, wejście bez stopni.", "Low-floor, step-free boarding."),
    ("tram", 1): ("Niska podłoga tylko w środkowym członie. Wsiadaj środkowymi drzwiami.",
                  "Low floor only in the middle section. Board through the middle doors."),
    ("tram", 0): ("Wysokie wejście, trzy stopnie przy każdych drzwiach.", "High-floor, three steps at every door."),
    ("bus", 2): ("Autobus niskopodłogowy, rampa przy drugich drzwiach.", "Low-floor bus, ramp at the second door."),
}
LOW_FLOOR = {0: "none", 1: "partial", 2: "full"}


def _get(path: str) -> dict | list:
    r = httpx.get(API + path, timeout=20, headers={"User-Agent": "HearWeGoKrk demo snapshot"})
    r.raise_for_status()
    return r.json()


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _slug(name: str) -> str:
    if name in STOP_IDS:
        return STOP_IDS[name]
    s = unicodedata.normalize("NFKD", name.replace("ł", "l").replace("Ł", "L"))
    s = "".join(c if c.isalnum() else "_" for c in s if not unicodedata.combining(c)).lower()
    return "_".join(filter(None, s.split("_")))


def fetch() -> dict:
    """Live vehicles of our lines (both directions) + one trip per line in our direction."""
    snap = {"fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"), "source": API,
            "lines": {}, "stops": {}}
    for kind in ("t", "b"):
        wanted = {c["number"]: c for c in LINES if c["type"] == kind}
        pos = _get(f"/positions/?type={kind}&last=0")["pos"]
        mine = [v for v in pos.values() if v.get("line") in wanted and v.get("trip")]
        with ThreadPoolExecutor(8) as ex:
            trips = list(ex.map(lambda v: _get(f"/trip/?type={kind}&id={v['trip']}")["data"], mine))
        for v, trip in zip(mine, trips):
            cfg = wanted[v["line"]]
            entry = snap["lines"].setdefault(cfg["id"], {"vehicles": {}, "trip": None})
            entry["vehicles"][v["type"]["num"]] = v["type"]
            names = [s["name"] for s in trip]
            if entry["trip"] is None and cfg["board"] in names and trip[-1]["name"].startswith(cfg["headsign"][:8]):
                entry["trip"] = trip
        for s in _get(f"/stops/?type={kind}"):
            if s.get("id"):
                snap["stops"][f"{kind}:{s['id']}"] = {"name": s["name"], "lat": s["lat"], "lon": s["lon"]}
    # Keep only the stops our trips use (the full list is ~400 kB).
    used = {f"{c['type']}:{s['stop']}" for c in LINES
            for s in (snap["lines"].get(c["id"], {}).get("trip") or [])}
    snap["stops"] = {k: v for k, v in snap["stops"].items() if k in used}
    return snap


def merge_previous(snap: dict) -> dict:
    """A line with no live trip (night, diversion) keeps what the previous snapshot had."""
    path = MOCK / "ttss_snapshot.json"
    if not path.exists():
        return snap
    old = json.loads(path.read_text(encoding="utf-8"))
    for cfg in LINES:
        new = snap["lines"].get(cfg["id"])
        if (not new or not new["trip"]) and cfg["id"] in old["lines"]:
            print(f"  {cfg['id']}: no live trip right now, keeping the previous snapshot")
            snap["lines"][cfg["id"]] = old["lines"][cfg["id"]]
            snap["stops"].update({k: v for k, v in old["stops"].items() if k not in snap["stops"]})
    return snap


def _vehicle(t: dict, mode: str, source: str = "ttss") -> dict:
    low = t["low"] if t["low"] in LOW_FLOOR else 2
    pl, en = HINTS.get((mode, low), HINTS[(mode, 2)] if (mode, 2) in HINTS else HINTS[("tram", 2)])
    return {
        "side_number": t["num"], "mode": mode, "model": MODELS.get(t["type"], t["type"]),
        "ttss_type": t["type"], "low_floor": LOW_FLOOR[low],
        "audio_stop_announcements": low > 0, "air_conditioning": bool(t.get("ac")),
        "boarding_hint_pl": pl, "boarding_hint_en": en, "source": source,
    }


def build(snap: dict) -> tuple[dict, dict]:
    old_stops = {s["id"]: s for s in json.loads((MOCK / "stops.json").read_text(encoding="utf-8"))["stops"]}
    old_places = json.loads((MOCK / "stops.json").read_text(encoding="utf-8"))["places"]
    stops, lines, vehicles = {}, [], {}
    extra = {v["num"]: v for v in ILLUSTRATIVE}

    for cfg in LINES:
        data = snap["lines"].get(cfg["id"])
        if not data or not data["trip"]:
            sys.exit(f"{cfg['id']}: no trip in the snapshot — run again while line {cfg['number']} is running")
        mode = "tram" if cfg["type"] == "t" else "bus"
        trip = data["trip"]
        i = next(k for k, s in enumerate(trip) if s["name"] == cfg["board"])
        t0, seq = _minutes(trip[i]["time"]), []
        for s in trip[i:]:
            if s["name"] in cfg.get("skip", []) or (seq and STOP_IDS.get(s["name"], _slug(s["name"])) == seq[-1]["stop"]):
                continue  # loop stops, or a terminus listed twice (arrival + departure platform)
            sid = _slug(s["name"])
            if sid not in stops:
                geo = snap["stops"].get(f"{cfg['type']}:{s['stop']}") or {}
                prev = old_stops.get(sid, {})
                stops[sid] = {
                    "id": sid, "name": s["name"], "ttss_stop_point": s["stop"],
                    "lat": round(geo.get("lat", prev.get("lat", 0.0)), 6),
                    "lon": round(geo.get("lon", prev.get("lon", 0.0)), 6),
                    "modes": [mode],
                    # Not in TTSS: kept from the hand-made file where we had it, else unknown.
                    "step_free_access": prev.get("step_free_access"),
                    "tactile_paving": prev.get("tactile_paving"),
                    "voice_departure_board": prev.get("voice_departure_board"),
                }
            elif mode not in stops[sid]["modes"]:
                stops[sid]["modes"].append(mode)
            seq.append({"stop": sid, "t": _minutes(s["time"]) - t0})

        fleet = [_vehicle(t, mode) for _, t in sorted(data["vehicles"].items())]
        first = cfg.get("first_vehicle")
        if first and first not in {v["side_number"] for v in fleet}:
            known = extra.get(first)
            if known is None:
                sys.exit(f"{cfg['id']}: {first} is not on line {cfg['number']} in this snapshot")
            fleet.insert(0, _vehicle(known, known["mode"], "illustrative"))
        fleet.sort(key=lambda v: v["side_number"] != first)  # demo vehicle first, rest by number
        fleet = fleet[:MAX_ROTATION]
        for v in fleet:
            vehicles[v["side_number"]] = v
        lines.append({
            "id": cfg["id"], "number": cfg["number"], "mode": mode, "headsign": cfg["headsign"],
            "first_departure_offset_min": cfg["first_departure_offset_min"], "headway_min": cfg["headway_min"],
            "vehicle_rotation": [v["side_number"] for v in fleet],
            "delay_pattern_min": cfg["delay_pattern_min"], "stops": seq,
        })

    stops_file = {
        "_meta": {
            "note": "Stop names, order and platform coordinates from Kraków TTSS (api.ttss.pl, used by beta.ttss.pl). "
                    "step_free_access / tactile_paving / voice_departure_board are not in TTSS: hand-made, null = unknown.",
            "snapshot": snap["fetched_at"], "generated_by": "scripts/ttss_snapshot.py",
            "demo_origin": "tauron_arena",
        },
        "stops": list(stops.values()),
        "places": old_places,
    }
    fleet_file = {
        "_meta": {
            "note": "Lines, stop order, travel times and vehicles (side number = 'numer boczny', model, low-floor, "
                    "air-con) from a TTSS snapshot. Headways, delays and boarding hints are curated for the demo. "
                    "Vehicles with source 'illustrative' are not in TTSS (scenario S5 only).",
            "snapshot": snap["fetched_at"], "generated_by": "scripts/ttss_snapshot.py",
            "timing": "All times are minutes relative to simulation start (see mock_realtime.reset_clock). "
                      "'t' = minutes from the venue stop, taken from the real TTSS trip.",
            "low_floor_values": "full | partial | none (TTSS 'low': 2 | 1 | 0)",
            "demo": "reset_clock(12) → HG935 (line 12) is on the road; reset_clock(0) → the first 14 is the high-floor RZ105.",
        },
        "lines": lines,
        "vehicles": list(vehicles.values()),
    }
    return stops_file, fleet_file


def _write(name: str, data: dict) -> None:
    (MOCK / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    if "--offline" in sys.argv:
        snap = json.loads((MOCK / "ttss_snapshot.json").read_text(encoding="utf-8"))
    else:
        print(f"Fetching {API} …")
        snap = merge_previous(fetch())
        _write("ttss_snapshot.json", snap)
    stops_file, fleet_file = build(snap)
    _write("stops.json", stops_file)
    _write("lines_and_vehicles.json", fleet_file)
    for line in fleet_file["lines"]:
        print(f"  {line['id']:5} {len(line['stops']):2} stops, {line['stops'][-1]['t']:2} min, "
              f"vehicles {', '.join(line['vehicle_rotation'])}")


if __name__ == "__main__":
    main()
