"""
wallet.py — mock wallet + the purchase state machine.

    prepare_ticket ──▶ PENDING ──(new user turn, "tak")──▶ confirm  ──▶ PURCHASED
                          │
                          ├──("nie" / "stop" / "anuluj")────▶ cancel ──▶ CANCELLED
                          └──(silence: retry once, then)────▶ cancel ──▶ CANCELLED

Safety rules enforced HERE, not only in the prompt (an LLM can be talked into anything):
  1. No money moves in prepare_ticket.
  2. confirm is rejected in the same user turn as prepare (the user must actually answer).
  3. A pending action hard-expires even if the timer task died.
"""

import copy
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from mock import mock_realtime as rt

# A ticket must still be valid this long after the ride is expected to end (delays on the way).
TICKET_MARGIN_MIN = 3

_SEED = json.loads((rt.DATA_DIR / "account_and_tickets.json").read_text(encoding="utf-8"))
_state = copy.deepcopy(_SEED)  # mutable copy; reset() restores the seed for each demo run


class WalletError(Exception):
    """Business error returned to the agent as {"error": code, "message": ...}."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class PendingAction:
    id: str
    kind: str                 # only "buy_ticket" for now
    params: dict              # ticket, side number, payment source
    created_turn: int         # turn in which prepare_ticket ran
    timeout_s: int
    retries: int = 0          # how many "I didn't hear you" retries were spoken
    created_at: float = field(default_factory=time.time)

    def hard_expired(self) -> bool:
        # Two timeout windows (ask + one retry) plus a small grace period.
        return time.time() - self.created_at > self.timeout_s * 2 + 5


# --- accessors -----------------------------------------------------------
def reset() -> None:
    global _state
    _state = copy.deepcopy(_SEED)


def user() -> dict:
    return _state["user"]


def catalog() -> list[dict]:
    return _state["ticket_catalog"]


def templates() -> dict:
    return _state["confirmation_templates"]


def _default_card() -> dict:
    return next(c for c in _state["wallet"]["cards"] if c["is_default"])


def _price_text(p: float) -> str:
    """4.0 -> '4,00' (Polish decimal comma)."""
    return f"{p:.2f}".replace(".", ",")


def can_speak_amounts(session) -> bool:
    """Privacy: speak money aloud only if allowed by the user's setting / headphones."""
    mode = user()["privacy"]["speak_amounts_aloud"]
    if mode == "always":
        return True
    if mode == "never":
        return False
    return session.headphones  # "headphones_only"


def _active_tickets() -> list[dict]:
    now = datetime.now().isoformat(timespec="seconds")
    return [t for t in _state["wallet"]["active_tickets"] if t["valid_until"] > now]


# --- ticket length -------------------------------------------------------
def _leg_min(leg: dict) -> int:
    return leg["minutes"] if leg["type"] == "walk" else leg["wait_min"] + leg["ride_min"]


def trip_minutes(session, side_number: str | None) -> int | None:
    """Minutes from now until the user leaves their last vehicle, or None if unknown.

    On a vehicle that rides a leg of the planned route: its live ETA to that leg's stop, plus the
    planned legs after it (transfers). On any other vehicle: to the end of its line. Not on a
    running vehicle: the planned route from when it was planned.
    """
    st = rt.vehicle_status(side_number) if side_number else None
    legs = session.plan["legs"] if session.plan else []
    if st:
        etas = {s["name"]: s["eta_min"] for s in st["remaining_stops"]}
        for i, leg in enumerate(legs):
            if leg["type"] == "ride" and leg["line_number"] == st["line_number"] and leg["to"] in etas:
                return etas[leg["to"]] + sum(_leg_min(x) for x in legs[i + 1:])
        return st["remaining_stops"][-1]["eta_min"] if st["remaining_stops"] else None
    if legs:
        end = session.plan["start_min"] + sum(_leg_min(x) for x in legs)
        return max(0, math.ceil(end - rt.now_min()))
    return None


def pick_ticket(minutes: int | None, fare: str = "full") -> dict:
    """The shortest ticket of this fare still valid TICKET_MARGIN_MIN after the ride ends
    (the longest one if none is long enough, the shortest one if the ride length is unknown)."""
    suffix = "_u" if fare == "reduced" else "_n"
    options = sorted((t for t in catalog() if t["id"].endswith(suffix)), key=lambda t: t["valid_min"])
    if minutes is None:
        return options[0]
    return next((t for t in options if t["valid_min"] >= minutes + TICKET_MARGIN_MIN), options[-1])


# --- tool implementations ------------------------------------------------
def get_balance(session) -> dict:
    bal = _state["wallet"]["balance_pln"]
    return {
        "balance_pln": bal,
        "balance_text": f"{_price_text(bal)} zł",
        "default_card": _default_card()["label_pl"],
        "speak_amount_aloud": can_speak_amounts(session),  # agent must respect this
        "active_tickets": _active_tickets(),
    }


def prepare_ticket(session, ticket_id: str | None = None, side_number: str | None = None,
                   fare: str = "full") -> dict:
    """ticket_id None: pick the ticket that lasts the whole ride (pick_ticket)."""
    side_number = side_number or session.current_vehicle
    if side_number and side_number not in rt.VEHICLES:
        veh = rt.find_vehicle(side_number)  # "HG 935", "935"...
        if veh is None:
            raise WalletError("unknown_vehicle", f"Vehicle '{side_number}' not found.")
        side_number = veh["side_number"]
    minutes = trip_minutes(session, side_number)
    if ticket_id is None:
        ticket = pick_ticket(minutes, fare)
    else:
        ticket = next((t for t in catalog() if t["id"] == ticket_id), None)
        if ticket is None:
            raise WalletError("unknown_ticket", f"No ticket '{ticket_id}'. Call list_tickets.")
    if ticket["requires_vehicle_side_number"] and not side_number:
        raise WalletError("missing_side_number",
                          "Vehicle unknown. Call match_boarded_vehicle first, or ask the user to say when they board.")

    price = ticket["price_pln"]
    # Pay from the in-app balance when possible, otherwise from the default card.
    source = "balance" if _state["wallet"]["balance_pln"] >= price else "card"
    card = _default_card()
    if session.lang == "pl":
        name = ticket["name_pl"]
        payment_label = "z salda" if source == "balance" else f"kartą {card['brand']} kończącą się na {card['last4']}"
    else:
        name = ticket["name_en"]
        payment_label = "from your balance" if source == "balance" else f"with your {card['brand']} ending in {card['last4']}"

    private = can_speak_amounts(session)
    key = f"purchase_{session.lang}_{'private' if private else 'public'}"
    text = templates()[key].format(ticket_name=name, price=_price_text(price),
                                   payment_label=payment_label, side_number=side_number)

    pa = PendingAction(
        id="pa_" + uuid.uuid4().hex[:6], kind="buy_ticket",
        params={"ticket": ticket, "side_number": side_number, "payment_source": source},
        created_turn=session.turn,
        timeout_s=user()["privacy"]["confirmation_timeout_s"],
    )
    session.pending = pa  # only one pending action per session; a new one replaces the old
    return {
        "pending_action_id": pa.id,
        "confirmation_text": text,   # the agent should say THIS, with all parameters
        "timeout_s": pa.timeout_s,
        "ticket_id": ticket["id"],
        "ticket": ticket,
        "side_number": side_number,
        "payment_source": source,
        "show_price": private,       # the frontend hides the price behind "Pokaż kwotę" if False
        "trip_min": minutes,         # ride left, None = unknown
        "covers_trip": minutes is None or ticket["valid_min"] >= minutes,
    }


def confirm(session, pending_action_id: str | None = None) -> dict:
    pa = session.pending
    if pa is None or (pending_action_id and pa.id != pending_action_id):
        raise WalletError("no_pending", "There is nothing to confirm.")
    if pa.created_turn == session.turn:
        raise WalletError("same_turn", "The user has not answered yet. Ask and wait for an explicit yes.")
    if pa.hard_expired():
        session.pending = None
        raise WalletError("expired", "The confirmation expired. Ask the user again.")

    t = pa.params["ticket"]
    if pa.params["payment_source"] == "balance":
        _state["wallet"]["balance_pln"] = round(_state["wallet"]["balance_pln"] - t["price_pln"], 2)
    now = datetime.now()
    bought = {
        "ticket_id": t["id"], "name_pl": t["name_pl"], "price_pln": t["price_pln"],
        "vehicle": pa.params["side_number"],
        "valid_from": now.isoformat(timespec="seconds"),
        "valid_until": (now + timedelta(minutes=t["valid_min"])).isoformat(timespec="seconds"),
        "paid_with": pa.params["payment_source"],
    }
    _state["wallet"]["active_tickets"].append(bought)
    _state["wallet"]["history"].insert(0, {"date": bought["valid_from"], "ticket_id": t["id"],
                                           "price_pln": t["price_pln"], "vehicle": bought["vehicle"]})
    session.pending = None
    return {"status": "purchased", "ticket": bought, "balance_pln": _state["wallet"]["balance_pln"]}


def cancel(session) -> dict:
    pa = session.pending
    session.pending = None
    if pa is None:
        return {"status": "nothing_to_cancel"}
    return {"status": "cancelled", "what": pa.kind, "ticket": pa.params["ticket"]["name_pl"]}
