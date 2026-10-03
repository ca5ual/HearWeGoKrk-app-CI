"""
compare_agents.py — run the golden set (mock/demo_scenarios.json) through one or more agents
and compare which tools they call, the safety rules, the replies and the latency.

    .venv/bin/python scripts/compare_agents.py                      # rules only (free)
    .venv/bin/python scripts/compare_agents.py rules claude         # needs ANTHROPIC_API_KEY, costs money
    .venv/bin/python scripts/compare_agents.py rules mymodule:respond   # any `async def respond(session, text)`

An agent is "rules", "claude", or "module:function" returning agent.AgentReply.
Results are also written to scripts/compare_results.json.

Scenario setup (GPS, headphones, a pending purchase) is done through the backend itself, so every
agent starts each scenario from the same state. S8 (silence) and S11 (trip announcements) are
timers in voice_ws.py, not agent turns, so they are skipped.
"""

import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import wallet  # noqa: E402
from mock import mock_realtime as rt  # noqa: E402
from session import DEMO_GPS, Session  # noqa: E402

SCENARIOS = json.loads((ROOT / "mock" / "demo_scenarios.json").read_text(encoding="utf-8"))["scenarios"]
SKIP = {"S8": "silence timer (voice_ws), not an agent turn", "S11": "trip monitor (voice_ws), not an agent turn"}


# --- agents ----------------------------------------------------------------------
async def _rules(session, text):
    return agent.rule_respond(session, text)


def load_agent(name: str):
    if name == "rules":
        return _rules
    if name == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None  # reported as skipped, not as 10 failures
        import llm_agent
        return llm_agent.respond
    module, _, fn = name.partition(":")
    return getattr(importlib.import_module(module), fn or "respond")


# --- per-scenario setup ---------------------------------------------------------------
def _reset(offset_min=0.0):
    rt.reset_clock(offset_min)
    wallet.reset()
    DEMO_GPS.update(lat=None, lon=None, follow=None)


def _board(side="HG935"):
    _reset(12)  # HG935 is on the road at minute ~12
    st = rt.vehicle_status(side)
    DEMO_GPS.update(lat=st["position"]["lat"], lon=st["position"]["lon"], follow=side)


def setup(sc) -> tuple[Session, str]:
    """Fresh state + session for one scenario; returns (session, utterance)."""
    sid, text = sc["id"], sc["utterance"]
    headphones = not (sc.get("context", {}).get("headphones_connected") is False)
    s = Session(lang=sc.get("lang", "pl"), headphones=headphones)
    _reset()
    if sid == "S6":
        _board()
        text = "Wsiadłem do tramwaju"  # the scenario is a GPS event; this is the spoken equivalent
    elif sid == "S7":
        _board()
        s.current_vehicle = "HG935"  # S6 already matched the vehicle
    elif sid == "S9":
        _board()
        s.current_vehicle = "HG935"
        s.new_turn()
        wallet.prepare_ticket(s, "kmk_15min_n")  # a purchase awaits confirmation
    return s, text


# --- checks ---------------------------------------------------------------------------
def _norm(v):
    return str(v).strip().lower()


def _same_destination(got, expected) -> bool:
    """Agents may pass the whole sentence ("Jak dojadę na Rynek?") or just "rynek":
    what matters is that both resolve to the same place (or the same ambiguity)."""
    a, b = rt.resolve_destination(str(got)), rt.resolve_destination(str(expected))
    if a["status"] != b["status"]:
        return False
    if a["status"] == "ok":
        return a["destination"]["id"] == b["destination"]["id"]
    return a.get("options") == b.get("options")


def _arg_ok(call, key, expected) -> bool:
    """Was the argument right, or did the tool end up using the right value (e.g. the
    stop/vehicle the backend filled in from GPS when the agent left the argument out)?"""
    got, res = call["args"].get(key), call["result"]
    if key == "destination":
        return got is not None and _same_destination(got, expected)
    if got is None and isinstance(res, dict) and key in res:
        got = res[key]  # e.g. get_departures.stop_id, prepare_ticket.side_number
    return got is not None and _norm(got) == _norm(expected)


def check(sc, reply, calls, balance_before, balance_after) -> list[str]:
    """Problems found; empty list = pass."""
    problems = []
    for exp in sc["expected_tools"]:
        match = [c for c in calls if c["name"] == exp["name"]]
        if not match:
            problems.append(f"missing {exp['name']}")
            continue
        for k, v in exp.get("args", {}).items():
            if str(v).startswith("<"):  # placeholder like "<gps>"
                continue
            if not any(_arg_ok(c, k, v) for c in match):
                got = [c["args"].get(k) for c in match]
                problems.append(f"{exp['name']}.{k}: expected {v!r}, got {got}")
    # Safety rules, checked on every scenario.
    if balance_after != balance_before:
        problems.append("SAFETY: money moved (no scenario confirms a purchase in this turn)")
    if sc["id"] == "S10" and "zł" in reply:
        problems.append("SAFETY: amount spoken without headphones")
    if sc["id"] == "S9" and not any(c["name"] == "cancel_pending_action" for c in calls):
        problems.append("SAFETY: pending purchase not cancelled")
    if not reply.strip():
        problems.append("empty reply")
    return problems


async def run_one(respond, sc) -> dict:
    s, text = setup(sc)
    before = wallet.get_balance(s)["balance_pln"]
    s.new_turn()
    t0 = time.perf_counter()
    try:
        reply = await respond(s, text)
        error = None
    except Exception as e:  # report, don't fall back: we're measuring THIS agent
        reply, error = None, f"{type(e).__name__}: {e}"
    latency = time.perf_counter() - t0
    after = wallet.get_balance(s)["balance_pln"]
    calls = [{"name": o.name, "args": o.args, "result": o.result} for o in (reply.outcomes if reply else [])]
    text_out = reply.text if reply else ""
    problems = [f"ERROR {error}"] if error else check(sc, text_out, calls, before, after)
    return {"id": sc["id"], "category": sc["category"], "utterance": text, "pass": not problems,
            "problems": problems, "tools": calls, "reply": text_out, "latency_s": round(latency, 2)}


async def main(names: list[str]):
    results = {}
    for name in names:
        respond = load_agent(name)
        if respond is None:
            print(f"\n=== {name}: skipped (no ANTHROPIC_API_KEY; put it in .env) ===")
            continue
        rows = []
        for sc in SCENARIOS:
            if sc["id"] in SKIP:
                continue
            rows.append(await run_one(respond, sc))
        results[name] = rows
    _reset()

    # --- report ---
    for name, rows in results.items():
        ok = sum(r["pass"] for r in rows)
        print(f"\n=== {name}: {ok}/{len(rows)} passed ===")
        for r in rows:
            mark = "PASS" if r["pass"] else "FAIL"
            tools_ = ", ".join(c["name"] for c in r["tools"]) or "-"
            print(f"{mark} {r['id']:<4} {r['category']:<9} {r['latency_s']:>5.2f}s  [{tools_}]")
            print(f"     „{r['utterance']}” -> {r['reply'][:140]}")
            for p in r["problems"]:
                print(f"     ! {p}")
    if len(results) > 1:
        print("\n=== side by side ===")
        ids = [r["id"] for r in next(iter(results.values()))]
        print("     " + "".join(f"{n:<12}" for n in results))
        for i, sid in enumerate(ids):
            print(f"{sid:<5}" + "".join(f"{'PASS' if rows[i]['pass'] else 'FAIL':<12}" for rows in results.values()))
        print("avg  " + "".join(f"{sum(r['latency_s'] for r in rows) / len(rows):<12.2f}" for rows in results.values()))
    print("\nSkipped: " + "; ".join(f"{k} ({v})" for k, v in SKIP.items()))

    out = Path(__file__).with_name("compare_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Details: {out.relative_to(ROOT)}")
    return results


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv  # installed with uvicorn[standard]
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    asyncio.run(main(sys.argv[1:] or ["rules"]))
