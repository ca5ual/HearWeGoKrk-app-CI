"""
llm_agent.py — Claude tool-calling agent, used by agent.respond() when AGENT=claude.

    respond(session, text) -> agent.AgentReply

Loop: user text (+ a one-line context note) -> Claude with the tools from tools.py ->
run each tool_use via tools.execute() -> send all tool_results back -> until Claude answers.

Safety does NOT depend on this prompt: wallet.py refuses confirm in the same turn as prepare,
and every purchase still needs an explicit "tak" in a new user turn.

Env:
    ANTHROPIC_API_KEY   (or any credential the Anthropic SDK resolves)
    AGENT_MODEL        default claude-opus-5-5
    AGENT_EFFORT       default low (voice: latency matters more than depth here)
"""

import json
import os

import anthropic

import tools

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("AGENT_EFFORT", "low")
MAX_TOOL_ROUNDS = 6       # a turn needs at most ~3 (e.g. match vehicle -> prepare ticket)
MAX_HISTORY_MESSAGES = 80  # start a fresh conversation after this (history is append-only)

# Server-side refusal fallback: if a safety classifier declines, the API re-runs the request
# on Anthropic's recommended fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You are HearWeGoKrk, a voice assistant for blind and visually impaired people using public \
transport in Kraków. Everything you write is read aloud by text-to-speech and shown in large \
type for a sighted companion.

How to answer:
- Answer in the language the user spoke (Polish or English). Default to Polish.
- Be short: one to three sentences. Put the most important facts first: line, how many \
minutes, and whether the vehicle is low-floor.
- Write for the ear: no markdown, lists, emoji or abbreviations. Write times as 16:25 and \
vehicle side numbers exactly as the tools give them.
- Use only facts from tool results. Never invent departures, delays, prices or vehicles. If a \
tool returns an error, say plainly what failed and what the user can do.
- Say "według danych na żywo" / "according to live data" when data_source is live or \
simulated_live, and "według rozkładu" / "according to the timetable" otherwise, whenever \
timing certainty matters (delays, "will it be late?").
- If the first vehicle has low_floor "none", warn about the high steps and offer the next \
low-floor one.
- If plan_route returns "ambiguous", ask one short question listing the options. Ask only \
about the unclear part.

Tickets and money (high risk):
- The ticket needs the vehicle's side number (numer boczny, e.g. HG935). If the user says it, \
call set_vehicle. Otherwise call match_boarded_vehicle (GPS); if that finds nothing, ask the \
user to read the side number from the sticker by the door.
- To buy, make sure the vehicle is known as above, then call prepare_ticket. Read \
its confirmation_text to the user word for word, then stop and wait.
- Call confirm_pending_action only when the user's newest message is an explicit yes to that \
purchase ("tak", "potwierdzam", "yes"). Anything unclear: ask again. Silence is not consent.
- "stop", "anuluj", "cancel" or "nie" while a purchase is pending: call cancel_pending_action \
immediately and say what was cancelled.
- If get_balance returns speak_amount_aloud false, do not say the amount. Ask whether to say \
it aloud, because the user has no headphones.
- Default ticket: kmk_15min_n (15-minute, full fare), unless the user asks for another.

Each user message starts with a [kontekst: ...] note from the app (headphones, current \
vehicle, pending purchase). It is app state, not something the user said.
"""

_client: anthropic.AsyncAnthropic | None = None


def _anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        # Voice turn: fail fast, so agent.respond() can fall back to the rule-based brain.
        _client = anthropic.AsyncAnthropic(timeout=20.0, max_retries=1)
    return _client


def _context_note(session) -> str:
    pa = session.pending
    parts = [
        f"język: {session.lang}",
        f"słuchawki: {'tak' if session.headphones else 'nie'}",
        f"pojazd: {session.current_vehicle or 'nieznany'}",
        f"oczekujący zakup: {pa.id + ' (' + pa.params['ticket']['name_pl'] + ')' if pa else 'brak'}",
    ]
    return "[kontekst: " + "; ".join(parts) + "]"


def _after_failure(session, outcomes) -> str:
    """Say what was already done when the API fails mid-turn."""
    bought = next((o.result for o in outcomes
                   if o.name == "confirm_pending_action" and o.result.get("status") == "purchased"), None)
    if bought:
        until = bought["ticket"]["valid_until"][11:16]
        return session.t(f"Kupione. Bilet ważny do {until}. Mam problem z połączeniem, resztę powtórz proszę.",
                         f"Done, ticket valid until {until}. I have a connection problem, please repeat the rest.")
    return session.t("Mam problem z połączeniem. Powtórz proszę.", "I have a connection problem. Please repeat.")


def _text_of(content) -> str:
    return " ".join(b.text.strip() for b in content if b.type == "text" and b.text.strip())


async def respond(session, text: str):
    from agent import AgentReply  # avoid a circular import at module load

    if len(session.history) > MAX_HISTORY_MESSAGES:
        session.history.clear()  # new conversation; never edit old turns (thinking blocks are bound to them)

    session.history.append({"role": "user", "content": f"{_context_note(session)}\n{text}"})
    outcomes: list[tools.ToolOutcome] = []

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = await _anthropic().beta.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=tools.tool_schemas_anthropic(),
                messages=session.history,
                output_config={"effort": EFFORT},
                cache_control={"type": "ephemeral"},  # system + tools + history prefix is reused every round
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIError:
            if not outcomes:
                raise  # nothing happened yet: agent.respond() lets the rule brain answer instead
            # Tools already ran this turn (maybe a purchase): don't let the rule brain redo the turn.
            return AgentReply(_after_failure(session, outcomes), outcomes)
        # Keep the full content (thinking + tool_use blocks), not just the text.
        session.history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            msg = session.t("Przepraszam, nie mogę w tym pomóc.", "Sorry, I can't help with that.")
            return AgentReply(msg, outcomes)

        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            reply = _text_of(response.content) or session.t(
                "Przepraszam, nie zrozumiałem. Powtórz proszę.", "Sorry, I didn't get that. Please repeat."
            )
            session.flags["last_text"] = reply  # for "powtórz" if we fall back to the rule brain
            return AgentReply(reply, outcomes)

        # Run calls in order (prepare -> confirm ordering matters), return all results in one message.
        results = []
        for call in calls:
            args = call.input if isinstance(call.input, dict) else {}
            outcome = tools.execute(session, call.name, args)
            outcomes.append(outcome)
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(outcome.result, ensure_ascii=False),
                "is_error": "error" in outcome.result,
            })
        session.history.append({"role": "user", "content": results})

    # Too many rounds: close the turn cleanly so the history stays valid.
    reply = session.t("Przepraszam, to trwa za długo. Spróbuj zapytać prościej.",
                      "Sorry, that took too long. Please try a simpler question.")
    return AgentReply(reply, outcomes)
