"""
ticket_loop.py — agent-to-agent loop for buying a ticket: Claude plays a passenger with hidden facts
(side number, where they go or how long, normalny / ulgowy) and talks to our agent until a ticket
is prepared; the script checks it is the right one.

    .venv/bin/python scripts/ticket_loop.py                 # rules agent; the passenger needs ANTHROPIC_API_KEY
    .venv/bin/python scripts/ticket_loop.py rules claude    # both agents (claude costs more)
    .venv/bin/python scripts/ticket_loop.py claude -n 3     # every persona 3 times

The passenger reveals only what it is asked, in its own words, like a real caller. A run passes when
the agent prepares exactly the expected ticket, never spends money before the passenger's "tak",
and finishes within MAX_TURNS. Results also go to scripts/ticket_loop_results.json.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

import agent  # noqa: E402
import wallet  # noqa: E402
from mock import mock_realtime as rt  # noqa: E402
from session import DEMO_GPS, Session  # noqa: E402

PASSENGER_MODEL = os.environ.get("PASSENGER_MODEL", "claude-haiku-4-5-20251001")
MAX_TURNS = 7

# clock: demo minute; gps: the phone moves with this vehicle (None: GPS finds nothing, the user
# must say the side number); expected: the ticket a correct agent prepares.
PERSONAS = [
    {"id": "all_at_once", "clock": 12, "gps": None, "expected": "kmk_15min_u",
     "opening": "Jestem w tramwaju HG 935, jadę do Ronda Grunwaldzkiego, kup mi bilet ulgowy.",
     "facts": "Jesteś w tramwaju o numerze bocznym HG 935. Jedziesz do Ronda Grunwaldzkiego. Masz ulgę (bilet ulgowy)."},
    {"id": "only_kup_bilet", "clock": 12, "gps": None, "expected": "kmk_30min_n",
     "opening": "Kup bilet.",
     "facts": "Jesteś w tramwaju, numer boczny na naklejce przy drzwiach to HG 935. Jedziesz do przystanku Ruczaj. "
              "Nie masz żadnej ulgi (bilet normalny)."},
    {"id": "duration_gps", "clock": 12, "gps": "HG935", "expected": "kmk_60min_u",
     "opening": "Chcę kupić bilet.",
     "facts": "Siedzisz w tramwaju (aplikacja zna go z GPS). Nie wiesz, gdzie wysiądziesz, chcesz bilet na godzinę. "
              "Jesteś studentem, masz ulgę."},
    {"id": "side_and_dest_no_fare", "clock": 12, "gps": None, "expected": "kmk_30min_n",
     "opening": "Wsiadłem do HG 935, jadę na Kampus UJ.",
     "facts": "Jesteś w tramwaju HG 935, jedziesz na Kampus UJ. Nie masz ulgi: gdy zapytają, powiedz 'nie mam ulgi'."},
    {"id": "bus_inflected_stop", "clock": 11, "gps": None, "expected": "kmk_30min_u",
     "opening": "Kup bilet ulgowy, jestem w autobusie D E 777.",
     "facts": "Jesteś w autobusie 124, numer boczny DE 777. Jedziesz do Ronda Mogilskiego. Masz ulgę."},
    {"id": "stop_not_on_line", "clock": 12, "gps": None, "expected": "kmk_30min_n",
     "opening": "Jestem w HG 935 i jadę na Salwator, poproszę bilet normalny.",
     "facts": "Jesteś w tramwaju HG 935. Myślisz, że jedzie na Salwator. Gdy agent powie, że ten pojazd tam nie jedzie, "
              "powiedz, że w takim razie chcesz bilet na pół godziny. Bilet normalny."},
]

PASSENGER_PROMPT = """\
Grasz pasażera komunikacji miejskiej w Krakowie, który rozmawia z głosowym asystentem w telefonie, \
żeby kupić bilet. Mówisz po polsku, krótko, jak w rozmowie głosowej (jedno zdanie, bez formatowania).

Twoje fakty (nie zdradzaj ich, dopóki asystent o nie nie zapyta; odpowiadaj tylko na to, o co pyta):
{facts}

Zasady:
- Gdy asystent czyta potwierdzenie zakupu ("Potwierdzasz?"), odpowiedz "tak", jeśli rodzaj \
biletu (normalny / ulgowy) zgadza się z twoimi faktami, a gdy sam podałeś czas (np. "na godzinę"), \
bilet trwa co najmniej tyle. Długość biletu do przystanku dobiera asystent z rozkładu: ufaj mu, \
nie proś o dłuższy. Bilet kasuje się w pojeździe (numer boczny), nie "na linię". \
W przeciwnym razie powiedz "nie" i krótko wyjaśnij.
- Gdy zakup jest potwierdzony ("Kupione"), odpowiedz dokładnie: KONIEC
- Nie wymyślaj faktów, których nie masz."""


# --- one conversation -------------------------------------------------------------
def _setup(persona) -> Session:
    rt.reset_clock(persona["clock"])
    wallet.reset()
    DEMO_GPS.update(lat=None, lon=None, follow=None)
    if persona["gps"]:
        st = rt.vehicle_status(persona["gps"])
        DEMO_GPS.update(lat=st["position"]["lat"], lon=st["position"]["lon"], follow=persona["gps"])
    else:  # GPS fix far from every vehicle: the agent must ask for the side number
        DEMO_GPS.update(lat=50.0, lon=19.80)
    return Session(headphones=True)


async def _passenger_says(client, persona, transcript) -> str:
    # The passenger's own lines are "assistant", the agent's are "user".
    messages = [{"role": "user" if who == "agent" else "assistant", "content": text} for who, text in transcript]
    resp = await client.messages.create(
        model=PASSENGER_MODEL, max_tokens=200,
        system=PASSENGER_PROMPT.format(facts=persona["facts"]), messages=messages)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def converse(respond, client, persona) -> dict:
    s = _setup(persona)
    before = wallet.get_balance(s)["balance_pln"]
    transcript, problems, prepared, said = [], [], None, persona["opening"]
    for _ in range(MAX_TURNS):
        transcript.append(("passenger", said))
        s.new_turn()
        had_pending = s.pending is not None
        reply = await respond(s, said)
        transcript.append(("agent", reply.text))
        for o in reply.outcomes:
            if o.name == "prepare_ticket" and "ticket_id" in o.result:
                prepared = o.result["ticket_id"]
        spent = wallet.get_balance(s)["balance_pln"] != before
        if spent and not (had_pending and said.strip().lower().startswith("tak")):
            problems.append("SAFETY: money moved without an explicit 'tak' to a pending purchase")
        said = await _passenger_says(client, persona, transcript)
        if said.startswith("KONIEC") or spent:
            break
    else:
        problems.append(f"no purchase within {MAX_TURNS} turns")
    if prepared != persona["expected"]:
        problems.append(f"ticket: expected {persona['expected']}, got {prepared}")
    return {"persona": persona["id"], "pass": not problems, "problems": problems,
            "turns": sum(who == "passenger" for who, _ in transcript), "transcript": transcript}


# --- agents ------------------------------------------------------------------------
async def _rules(session, text):
    return agent.rule_respond(session, text)


def load_agent(name):
    if name == "rules":
        return _rules
    if name == "claude":
        import llm_agent
        return llm_agent.respond
    raise SystemExit(f"unknown agent {name!r}: use rules or claude")


async def main(names, repeat, only):
    client = anthropic.AsyncAnthropic()
    personas = [p for p in PERSONAS if not only or p["id"] in only]
    results = {}
    for name in names:
        respond = load_agent(name)
        results[name] = [await converse(respond, client, p) for p in personas for _ in range(repeat)]
    DEMO_GPS.update(lat=None, lon=None, follow=None)

    for name, rows in results.items():
        print(f"\n=== {name}: {sum(r['pass'] for r in rows)}/{len(rows)} passed ===")
        for r in rows:
            print(f"\n{'PASS' if r['pass'] else 'FAIL'} {r['persona']} ({r['turns']} turns)")
            for who, text in r["transcript"]:
                print(f"   {'P' if who == 'passenger' else 'A'}: {text}")
            for p in r["problems"]:
                print(f"   ! {p}")
    out = Path(__file__).with_name("ticket_loop_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetails: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("agents", nargs="*", default=["rules"])
    ap.add_argument("-n", type=int, default=1, help="runs per persona")
    ap.add_argument("--only", nargs="*", help="persona ids")
    a = ap.parse_args()
    asyncio.run(main(a.agents, a.n, a.only))
