"""
tools.py — everything the agent can DO, in one registry.

An agent only needs two things from this file:
    tool_schemas_anthropic()        -> pass to the LLM API
    execute(session, name, args)    -> run a tool call, get a ToolOutcome

To switch from mock to live data later, change `provider` below to a module that
exposes the same functions as mock_realtime (get_departures, plan_route, ...).
"""

from dataclasses import dataclass
from typing import Any, Callable

import wallet
from mock import mock_realtime

provider = mock_realtime  # <- swap for a live GTFS-RT / TTSS adapter with the same API


@dataclass
class ToolOutcome:
    name: str
    args: dict
    result: dict                     # what goes back to the LLM as the tool result
    ui: dict | None = None           # {"component": ..., "data": ...} for the phone, or None
    pending: dict | None = None      # set when a purchase now awaits confirmation


@dataclass
class Tool:
    fn: Callable[..., dict]
    description: str
    parameters: dict                 # JSON Schema of the arguments
    ui_component: str | None = None  # which FRONTEND.md screen renders the result
    ui_key: str | None = None        # render result[ui_key] instead of the whole result


# --- helpers -------------------------------------------------------------
def _nearest_stop_id(lat: float, lon: float) -> str:
    return min(provider.STOPS.values(),
               key=lambda s: provider._haversine_m(lat, lon, s["lat"], s["lon"]))["id"]


# --- tool functions (all take the session first) ---------------------------
def plan_route(session, destination: str, prefer_low_floor: bool | None = None) -> dict:
    if prefer_low_floor is None:
        prefer_low_floor = wallet.user()["accessibility_profile"]["prefers_low_floor"]
    res = provider.plan_route(destination, prefer_low_floor=prefer_low_floor)
    if res.get("status") == "ok":
        legs = res["best"]["legs"]
        last = max((i for i, leg in enumerate(legs) if leg["type"] == "ride"), default=None)
        # Where to get off (for the "wysiadasz za 2 przystanki" announcements) and the legs the
        # ticket must cover (the walk after the last ride needs none). Walk-only: nothing to ride.
        session.target_stop_name = legs[last]["to"] if last is not None else None
        session.plan = ({"legs": legs[:last + 1], "start_min": provider.now_min()}
                        if last is not None else None)
    return res


def get_departures(session, stop_id: str | None = None, line_id: str | None = None,
                   low_floor_only: bool = False, limit: int = 5) -> dict:
    stop_id = stop_id or _nearest_stop_id(*session.location)
    if stop_id not in provider.STOPS:
        return {"error": "unknown_stop", "message": f"No stop '{stop_id}'."}
    deps = provider.get_departures(stop_id, line_id=line_id, low_floor_only=low_floor_only, limit=limit)
    return {"stop_id": stop_id, "stop_name": provider.STOPS[stop_id]["name"], "departures": deps}


def match_boarded_vehicle(session, lat: float | None = None, lon: float | None = None,
                          line_id: str | None = None) -> dict:
    if lat is None or lon is None:
        lat, lon = session.location
    match = provider.match_boarded_vehicle(lat, lon, line_id=line_id)
    if match is None:
        return {"matched": False}
    side = match["vehicle"]["side_number"]
    session.current_vehicle = side  # this is the auto-filled side number for the ticket
    return {"matched": True, **match, "trip": provider.vehicle_status(side)}


def set_vehicle(session, side_number: str) -> dict:
    """The user said or read the side number (it is printed inside every vehicle)."""
    veh = provider.find_vehicle(side_number)
    if veh is None:
        return {"error": "unknown_vehicle",
                "message": f"No vehicle '{side_number}'. Ask the user to read the side number again, "
                           "e.g. 'HG 935' (two letters, three digits, on a sticker by the door)."}
    session.current_vehicle = veh["side_number"]  # used by prepare_ticket
    st = provider.vehicle_status(veh["side_number"])
    return {"matched": True, "vehicle": provider._vehicle_info(veh),
            "line_number": st["line_number"] if st else None, "trip": st}


def vehicle_status(session, side_number: str | None = None) -> dict:
    side_number = side_number or session.current_vehicle
    if not side_number:
        return {"error": "no_vehicle", "message": "Unknown vehicle. Call match_boarded_vehicle."}
    st = provider.vehicle_status(side_number)
    return st if st else {"error": "not_running", "message": f"{side_number} is not on a trip now."}


def list_tickets(session, fare: str | None = None) -> dict:
    """fare: 'reduced' | 'full' | None (both)."""
    items = wallet.catalog()
    if fare == "reduced":
        items = [t for t in items if t["id"].endswith("_u")]
    elif fare == "full":
        items = [t for t in items if t["id"].endswith("_n")]
    return {"tickets": items}


def get_balance(session) -> dict:
    return wallet.get_balance(session)


def prepare_ticket(session, ticket_id: str | None = None, side_number: str | None = None,
                   fare: str = "full") -> dict:
    return wallet.prepare_ticket(session, ticket_id, side_number, fare)


def confirm_pending_action(session, pending_action_id: str | None = None) -> dict:
    return wallet.confirm(session, pending_action_id)


def cancel_pending_action(session) -> dict:
    return wallet.cancel(session)


# --- registry ------------------------------------------------------------
def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TOOLS: dict[str, Tool] = {
    "plan_route": Tool(
        plan_route,
        "Plan a public transport route from the user's position to a destination in Kraków. "
        "Pass the destination as the user said it (e.g. 'rynek', 'agh'). If status is 'ambiguous', "
        "ask the user to pick one of `options`; if 'not_found', ask them to rephrase.",
        _obj({"destination": {"type": "string"},
              "prefer_low_floor": {"type": "boolean", "description": "Defaults to the user's profile."}},
             ["destination"]),
        ui_component="route_results"),
    "get_departures": Tool(
        get_departures,
        "Next departures from a stop (default: the stop nearest to the user). Each departure has "
        "eta_min, delay_min, data_source and vehicle.low_floor ('full'|'partial'|'none'). "
        "If the first vehicle has low_floor 'none', warn the user and mention the next low-floor one.",
        _obj({"stop_id": {"type": "string"},
              "line_id": {"type": "string", "description": "e.g. 'T1', 'T12', 'T14', 'B124'"},
              "low_floor_only": {"type": "boolean"},
              "limit": {"type": "integer"}}),
        ui_component="departures"),
    "match_boarded_vehicle": Tool(
        match_boarded_vehicle,
        "Detect which vehicle the user is in from GPS. Call when the user says they boarded, or before "
        "buying a ticket. Stores the side number for prepare_ticket.",
        _obj({"line_id": {"type": "string"}}),
        ui_component="trip_live", ui_key="trip"),
    "set_vehicle": Tool(
        set_vehicle,
        "Set the user's vehicle from its side number (numer boczny), when the user says or reads it, "
        "e.g. 'jestem w HG 935', or when match_boarded_vehicle found nothing. Pass what the user said; "
        "'HG 935', 'hg935' or just '935' all work. Stores the side number for prepare_ticket.",
        _obj({"side_number": {"type": "string"}}, ["side_number"]),
        ui_component="trip_live", ui_key="trip"),
    "vehicle_status": Tool(
        vehicle_status,
        "Current position and remaining stops (with ETAs) of the user's vehicle.",
        _obj({"side_number": {"type": "string"}}),
        ui_component="trip_live"),
    "list_tickets": Tool(
        list_tickets,
        "Ticket catalog with prices. fare: 'reduced' or 'full'.",
        _obj({"fare": {"type": "string", "enum": ["reduced", "full"]}})),
    "get_balance": Tool(
        get_balance,
        "Wallet balance and active tickets. If speak_amount_aloud is false, do NOT say the amount; "
        "ask whether to say it aloud first.",
        _obj({})),
    "prepare_ticket": Tool(
        prepare_ticket,
        "Prepare (NOT buy) a ticket for the current vehicle. Say `confirmation_text` exactly and wait "
        "for an explicit yes in the next user turn. Omit ticket_id: the backend picks the shortest "
        "ticket valid for the rest of the ride (trip_min). Pass ticket_id only when the user asks for "
        "a specific ticket; if covers_trip is then false, warn that it ends before the ride does.",
        _obj({"ticket_id": {"type": "string"}, "side_number": {"type": "string"},
              "fare": {"type": "string", "enum": ["full", "reduced"],
                       "description": "'reduced' only if the user says they have a discount (ulga)."}}),
        ui_component="ticket_confirm"),
    "confirm_pending_action": Tool(
        confirm_pending_action,
        "Execute the pending purchase. ONLY after the user explicitly said yes in a new turn.",
        _obj({"pending_action_id": {"type": "string"}})),
    "cancel_pending_action": Tool(
        cancel_pending_action,
        "Cancel any pending purchase. Call immediately on 'stop', 'anuluj', 'cancel' or 'nie'.",
        _obj({})),
}


def tool_schemas_anthropic() -> list[dict]:
    return [{"name": n, "description": t.description, "input_schema": t.parameters} for n, t in TOOLS.items()]


_NO_UI_STATUSES = {"ambiguous", "not_found", "no_route"}


def execute(session, name: str, args: dict | None = None) -> ToolOutcome:
    """Run one tool call. Never raises: errors come back as {"error": ...} for the LLM to handle."""
    args = args or {}
    tool = TOOLS.get(name)
    if tool is None:
        result: dict[str, Any] = {"error": "unknown_tool", "message": f"No tool '{name}'."}
    else:
        try:
            result = tool.fn(session, **args)
        except wallet.WalletError as e:
            result = {"error": e.code, "message": e.message}
        except TypeError as e:  # wrong / missing arguments from the LLM
            result = {"error": "bad_arguments", "message": str(e)}
        except Exception as e:  # e.g. wrong argument types; keep the turn alive, let the LLM recover
            print(f"[tools] {name}({args}) failed: {e!r}")
            result = {"error": "tool_failed", "message": f"{type(e).__name__}: {e}"}

    ui = None
    ok = "error" not in result and result.get("status") not in _NO_UI_STATUSES and result.get("matched", True)
    if tool and tool.ui_component and ok:
        data = result.get(tool.ui_key) if tool.ui_key else result
        if data:
            ui = {"component": tool.ui_component, "data": data}

    pending = result if name == "prepare_ticket" and "pending_action_id" in result else None
    session.log_tool(name, args, result)
    return ToolOutcome(name, args, result, ui, pending)
