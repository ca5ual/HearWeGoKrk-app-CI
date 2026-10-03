"""
agent.py — the agent interface + a rule-based FALLBACK brain.

    async def respond(session, text) -> AgentReply

With AGENT=claude, llm_agent.py (Claude tool calling) answers. If that call raises
(no WiFi on stage, rate limit...), we automatically fall back to the rule-based brain
below, which handles the whole demo script on its own.
"""

import os
import re
from dataclasses import dataclass, field

import tools
import wallet

# AGENT=claude -> llm_agent.py (Claude tool calling). Unset -> rule-based brain only.
USE_LLM = os.environ.get("AGENT", "").lower() == "claude"


@dataclass
class AgentReply:
    text: str                                         # what to say (and show)
    outcomes: list = field(default_factory=list)      # list[tools.ToolOutcome]


async def respond(session, text: str) -> AgentReply:
    # Nothing heard (silence, or no speech-to-text yet): ask to repeat, don't spend an LLM call.
    if USE_LLM and text.strip():
        try:
            import llm_agent  # imported lazily: the rule brain must work without the anthropic package
            return await llm_agent.respond(session, text)
        except Exception as e:  # never let the demo die on an API error
            print(f"[agent] LLM failed, using fallback: {e!r}")
    return rule_respond(session, text)


# =========================================================================
# Rule-based fallback brain
# =========================================================================
_STOP = re.compile(r"\b(stop|anuluj|cancel)\b", re.I)
_YES = re.compile(r"\b(tak|potwierdzam|zgoda|dobrze|yes|confirm|okay|ok)\b", re.I)
_NO = re.compile(r"\b(nie|no)\b", re.I)
_BALANCE = re.compile(r"(saldo|ile mam|pieni[eę]dz|balance|how much money)", re.I)
_BOARD = re.compile(r"(wsiad[łl]|jestem w|i'?m on|boarded|got on)", re.I)
_BUY = re.compile(r"(kup|bilet|ticket|buy)", re.I)
_SIDE = re.compile(r"(numer boczny|numer pojazdu|pojazd|side number|vehicle)", re.I)
_DEPART = re.compile(r"(kiedy|nast[eę]pn|odjazd|next|when)", re.I)
_LATE = re.compile(r"(sp[oó][źz]ni|op[oó][źz]ni|\blate\b|\bdelay)", re.I)
_REPEAT = re.compile(r"(powt[oó]rz|repeat|say again)", re.I)

# Spoken line names -> line ids. Order matters: longer phrases first.
_LINE_WORDS = [("czternast", "T14"), ("dwunast", "T12"), ("jedynk", "T1"), (r"\b124\b", "B124"),
               (r"\b14\b", "T14"), (r"\b12\b", "T12"), (r"\b1\b", "T1")]

_MODE_PL = {"tram": "tramwaj", "bus": "autobus"}
_MODE_EN = {"tram": "tram", "bus": "bus"}


def _minutes_pl(n: int) -> str:
    """Polish plural after 'za': 1 minutę, 2-4 minuty, 5+ minut (but 12-14 minut)."""
    if n == 1:
        return "minutę"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "minuty"
    return "minut"


def _mins(session, n: int) -> str:
    return f"{n} {_minutes_pl(n)}" if session.lang == "pl" else f"{n} minute{'s' if n != 1 else ''}"


def _floor_phrase(session, vehicle: dict) -> str:
    lf = vehicle["low_floor"]
    if lf == "full":
        return session.t("niskopodłogowy", "low-floor")
    if lf == "partial":
        hint = session.t(vehicle["boarding_hint_pl"], vehicle["boarding_hint_en"]).rstrip(".")
        return hint[:1].lower() + hint[1:]  # read mid-sentence, after a comma
    return session.t("uwaga, wysokie stopnie", "careful, high steps")


def _say_route(session, res: dict) -> str:
    best = res["best"]
    parts = []
    for i, leg in enumerate(l for l in best["legs"] if l["type"] == "ride"):
        mode = (_MODE_PL if session.lang == "pl" else _MODE_EN)[leg["mode"]]
        if i == 0:
            parts.append(session.t(
                f"{mode.capitalize()} {leg['line_number']} z przystanku {leg['from']} za {_mins(session, leg['wait_min'])}, "
                f"o {leg['departure']}, {_floor_phrase(session, leg['vehicle'])}.",
                f"{mode.capitalize()} {leg['line_number']} from {leg['from']} in {_mins(session, leg['wait_min'])}, "
                f"at {leg['departure']}, {_floor_phrase(session, leg['vehicle'])}."))
        else:
            parts.append(session.t(f"Potem {mode} {leg['line_number']}.", f"Then {mode} {leg['line_number']}."))
    parts.append(session.t(f"Na miejscu o {best['arrival']}.", f"You'll arrive at {best['arrival']}."))
    return " ".join(parts)


def _say_departures(session, res: dict, certainty: bool = False) -> str:
    """certainty: the user asked whether it will be late -> say where the timing comes from."""
    deps = res["departures"]
    if not deps:
        return session.t("Nie widzę teraz żadnych odjazdów.", "I can't see any departures right now.")
    d0 = deps[0]
    mode = (_MODE_PL if session.lang == "pl" else _MODE_EN)[d0["mode"]]
    text = session.t(f"{mode.capitalize()} {d0['line_number']} za {_mins(session, d0['eta_min'])}",
                     f"{mode.capitalize()} {d0['line_number']} in {_mins(session, d0['eta_min'])}")
    if certainty:
        live = d0["data_source"] in ("live", "simulated_live")
        source = (session.t("Według danych na żywo", "According to live data") if live
                  else session.t("Według rozkładu", "According to the timetable"))
        text = f"{source}: {text[0].lower()}{text[1:]}"
    if d0["delay_min"]:
        text += session.t(f", ma {_mins(session, d0['delay_min'])} opóźnienia",
                          f", {_mins(session, d0['delay_min'])} late")
    elif certainty:
        text += session.t(", bez opóźnienia", ", on time")
    if d0["vehicle"]["low_floor"] == "none":
        nxt = next((d for d in deps[1:] if d["line_id"] == d0["line_id"] and d["vehicle"]["low_floor"] != "none"), None)
        text += session.t(", ale to stary tramwaj z wysokimi stopniami.", ", but it's an old vehicle with high steps.")
        if nxt:
            session.flags["offer"] = "wait"
            text += session.t(f" Następny niskopodłogowy za {_mins(session, nxt['eta_min'])}. Poczekać na niego?",
                              f" The next low-floor one is in {_mins(session, nxt['eta_min'])}. Wait for it?")
        return text
    return text + ", " + _floor_phrase(session, d0["vehicle"]) + "."


def rule_respond(session, text: str) -> AgentReply:
    t = text.strip()
    out: list = []

    def run(name, **args):
        o = tools.execute(session, name, args)
        out.append(o)
        return o.result

    if not t:
        return AgentReply(session.t("Nie usłyszałem, powtórz proszę.", "I didn't catch that, please repeat."))

    if _REPEAT.search(t) and session.flags.get("last_text"):
        return AgentReply(session.flags["last_text"])

    # 1) Emergency stop always wins.
    if _STOP.search(t):
        r = run("cancel_pending_action")
        session.flags.pop("offer", None)
        msg = session.t("Anulowałem zakup biletu." if r["status"] == "cancelled" else "Zatrzymałem. Nic nie było w toku.",
                        "I cancelled the ticket purchase." if r["status"] == "cancelled" else "Stopped. Nothing was in progress.")
        return _remember(session, AgentReply(msg, out))

    # 2) A purchase is waiting for an answer.
    if session.pending is not None:
        if _YES.search(t):
            r = run("confirm_pending_action", pending_action_id=session.pending.id)
            if "error" in r:
                return _remember(session, AgentReply(session.t("Nie udało się kupić biletu.", "The purchase failed."), out))
            return _remember(session, AgentReply(session.t(
                f"Kupione. Bilet ważny do {r['ticket']['valid_until'][11:16]}, skasowany w pojeździe {r['ticket']['vehicle']}.",
                f"Done. Ticket valid until {r['ticket']['valid_until'][11:16]}, validated in {r['ticket']['vehicle']}."), out))
        if _NO.search(t):
            run("cancel_pending_action")
            return _remember(session, AgentReply(session.t("Dobrze, nie kupuję.", "OK, not buying."), out))
        return AgentReply(session.t("Czy kupić bilet? Powiedz tak albo nie.", "Should I buy the ticket? Say yes or no."))

    # 3) Answers to an offer we made in the previous turn.
    offer = session.flags.pop("offer", None)
    if offer and _YES.search(t):
        if offer == "say_balance":
            bal = wallet.get_balance(session)
            return _remember(session, AgentReply(session.t(f"Masz {bal['balance_text']}.", f"You have {bal['balance_text']}."), out))
        if offer == "wait":
            return _remember(session, AgentReply(session.t("Dobrze, dam znać, gdy będzie podjeżdżał.",
                                                           "OK, I'll tell you when it's arriving."), out))
        if offer == "buy":
            t = "kup bilet"  # fall through to the buy branch below

    # 4) Intents.
    if _BALANCE.search(t):
        r = run("get_balance")
        if r["speak_amount_aloud"]:
            msg = session.t(f"Masz {r['balance_text']}.", f"You have {r['balance_text']}.")
        else:
            session.flags["offer"] = "say_balance"
            msg = session.t("Jesteś bez słuchawek. Podać saldo na głos?", "You're not wearing headphones. Say the balance aloud?")
        return _remember(session, AgentReply(msg, out))

    # The user said the side number ("jestem w HG 935", "numer boczny 935"): no GPS needed.
    if (_BOARD.search(t) or _BUY.search(t) or _SIDE.search(t)) and tools.provider.find_vehicle(t):
        r = run("set_vehicle", side_number=t)
        v = r["vehicle"]
        if not _BUY.search(t):
            session.flags["offer"] = "buy"
            return _remember(session, AgentReply(session.t(
                f"Jesteś w pojeździe {v['side_number']}"
                + (f", linia {r['line_number']}" if r["line_number"] else "") + ". Kupić bilet 15-minutowy?",
                f"You're in vehicle {v['side_number']}"
                + (f", line {r['line_number']}" if r["line_number"] else "") + ". Buy a 15-minute ticket?"), out))
    elif _BOARD.search(t) or (_BUY.search(t) and not session.current_vehicle):
        r = run("match_boarded_vehicle")
        if not r.get("matched"):
            return _remember(session, AgentReply(session.t(
                "Nie widzę jeszcze, w którym pojeździe jesteś. Powiedz numer boczny z naklejki przy drzwiach, "
                "na przykład HG 935.",
                "I can't tell which vehicle you're in yet. Say the side number from the sticker by the door, "
                "for example HG 935."), out))
        v = r["vehicle"]
        if not _BUY.search(t):
            session.flags["offer"] = "buy"
            return _remember(session, AgentReply(session.t(
                f"Jesteś w linii {r['line_number']}, pojazd {v['side_number']}. Kupić bilet 15-minutowy?",
                f"You're on line {r['line_number']}, vehicle {v['side_number']}. Buy a 15-minute ticket?"), out))

    if _BUY.search(t):
        r = run("prepare_ticket", ticket_id="kmk_15min_n")
        if "error" in r:
            return _remember(session, AgentReply(session.t("Nie mogę teraz przygotować biletu.",
                                                           "I can't prepare a ticket right now."), out))
        return _remember(session, AgentReply(r["confirmation_text"], out))

    if _DEPART.search(t) or _LATE.search(t):
        line_id = next((lid for pat, lid in _LINE_WORDS if re.search(pat, t, re.I)), None)
        r = run("get_departures", line_id=line_id)
        return _remember(session, AgentReply(_say_departures(session, r, certainty=bool(_LATE.search(t))), out))

    # 5) Default: treat the utterance as a destination.
    r = run("plan_route", destination=t)
    if r["status"] == "ambiguous":
        msg = session.t(f"Masz na myśli {' czy '.join(r['options'])}?", f"Do you mean {' or '.join(r['options'])}?")
    elif r["status"] == "not_found":
        msg = session.t("Nie znam tego miejsca. Spróbuj na przykład: Rynek, AGH albo Dworzec Główny.",
                        "I don't know that place. Try, for example: Main Square, AGH or the main station.")
    elif r["status"] == "no_route":
        msg = session.t("Nie znalazłem teraz połączenia.", "I couldn't find a connection right now.")
    else:
        msg = _say_route(session, r)
    return _remember(session, AgentReply(msg, out))


def _remember(session, reply: AgentReply) -> AgentReply:
    """Store the last reply so 'powtórz' works."""
    session.flags["last_text"] = reply.text
    return reply
