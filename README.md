# HearWeGoKrk 🎧🚋

Voice-first public transport assistant for blind and visually impaired people in Kraków.
One big button (Shazam-style): plan a route, hear live departures, check whether the vehicle
is low-floor, buy a ticket that lasts the whole ride with the **vehicle side number filled in
automatically**, and get told when to get off.

HackYeah 2026 · Smart City category (Bank Pekao).

---

## 1. Architecture

```
React Native (Expo)  ──audio + GPS──▶  FastAPI  ──▶  ElevenLabs Scribe (speech → text)
        ▲                                  │
        │                                  ▼
        │                  Claude tool calling (llm_agent.py)
        │                  └─ falls back to the rule-based brain (agent.py)
        │                                  │
        │                    tools ──▶ mock_realtime.py (or live GTFS-RT / TTSS)
        │                                  │         wallet / tickets (mock)
        │                                  ▼
        └──────audio + text + haptic──  ElevenLabs (text → speech)
```

- **Speech to text**: ElevenLabs Scribe (`speech.py`). It accepts the AAC audio Android records, so no GPU or local model is needed.
- **Agent**: with `AGENT=claude`, Claude calls the tools (`llm_agent.py`). If the API call fails (no Wi-Fi on stage, rate limit), the rule-based brain in `agent.py` answers instead and handles the whole demo script on its own. Without `AGENT`, only the rule-based brain runs.
- **Text to speech**: ElevenLabs streams the spoken reply in Polish or English. Without a key, the phone speaks `reply_text` with its own voice.
- Every agent reply is sent as **audio + text** (text shown on screen for a sighted companion, and available for "powtórz / repeat").
- Money safety lives in `wallet.py`, not in the prompt: no money moves in `prepare_ticket`, confirm is refused in the same turn, and a pending purchase hard-expires.

## 2. Repo layout

```
app.py                FastAPI app: REST endpoints, demo controls
voice_ws.py           WebSocket: audio in → STT → agent → TTS → audio out, confirmation + trip timers
agent.py              agent entry point + rule-based fallback brain
llm_agent.py          Claude tool-calling agent (AGENT=claude)
tools.py              tool registry: thin wrappers around mock_realtime + wallet
wallet.py             mock wallet, ticket choice by ride length, purchase state machine
session.py            per-conversation state
speech.py             ElevenLabs speech-to-text and text-to-speech
mock/                 JSON files + mock_realtime.py (section 3)
scripts/              TTSS snapshot, agent comparison on the golden set
tests/
mobile/src/
  app/                screens (expo-router): Mów, Trasa, Rozkłady, trip, settings, help
  agent/              AgentContext (WebSocket + state), audio.ts, location.ts
  components/         route cards, departures, confirmation sheet, talk button
```

## 3. Running

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --env-file .env

cd mobile && npm install && npx expo start   # scan the QR code with Expo Go
```

- The phone must be on the same Wi-Fi as the laptop. The app connects to `http://<laptop-ip>:8000`
  by default (the host running `expo start`); change it in Ustawienia or with `EXPO_PUBLIC_BACKEND_URL` in `mobile/.env`.
- `GET /health` shows whether the LLM, STT and TTS are configured (`llm`, `stt`, `tts`).
- Interactive API docs: `http://localhost:8000/docs`.

### Tests

```bash
.venv/bin/python -m pytest -q                              # backend, free (Claude and ElevenLabs are faked)
.venv/bin/python scripts/compare_agents.py                 # golden set, rule-based brain (free)
.venv/bin/python scripts/compare_agents.py rules claude    # same set with Claude (needs ANTHROPIC_API_KEY, costs money)
cd mobile && npx tsc --noEmit && npx expo lint
```

## 4. Mock data (`mock/`)

| File | Contents |
|---|---|
| `ttss_snapshot.json` | Raw extract from Kraków TTSS (api.ttss.pl, the backend of beta.ttss.pl): vehicles and real trips |
| `stops.json` | Real stop names, order and platform coordinates from TTSS; step-free / tactile / voice-board flags (hand-made, `null` = unknown) |
| `lines_and_vehicles.json` | Trams 1, 12, 14 and bus 124 from TAURON Arena with real stop order and travel times; real vehicles with side number (*numer boczny*, e.g. `HG935`), model, `low_floor` (full/partial/none), air-con |
| `routes.json` | Route templates from the venue, destination aliases, ambiguous aliases ("rondo") |
| `account_and_tickets.json` | Demo persona, wallet, mock card, ticket catalog (15, 30, 60 and 90 min, full and reduced fare), confirmation templates |
| `demo_scenarios.json` | 12-case golden set: typical / hard / high-risk |
| `mock_realtime.py` | Simulator: departures count down, vehicles move, delays appear |

Smoke test: `.venv/bin/python -m mock.mock_realtime`

Refresh from live TTSS (run while trams are running): `.venv/bin/python scripts/ttss_snapshot.py`.
It rewrites `ttss_snapshot.json`, `stops.json` and `lines_and_vehicles.json`; headways, delays,
boarding hints and the demo vehicle order are set at the top of the script.

**Before the demo, call `POST /demo/reset`** (or Ustawienia → Tryb demo → Reset demo): the first tram 14 is then
the high-floor RZ105 running 3 min late, and the next one (HY712) is low-floor. That is scenario S5. RZ105 is the
only vehicle not from TTSS (`"source": "illustrative"`): Kraków's live fleet no longer has fully high-floor trams.
With a 12-minute offset tram 12 **HG935** is on the road: that's the vehicle the ticket demo boards.

⚠️ Ticket prices are placeholders (check ztp.krakow.pl).

## 5. Contracts

### 5.1 Agent tools (`tools.py`)

| Tool | Args | Returns |
|---|---|---|
| `plan_route` | `destination`, `prefer_low_floor?` (default: user profile) | `status` ok / ambiguous / not_found / no_route, `best`, `alternatives`, `data_source`. Remembers the stop to get off at and the legs to ride (ticket length) |
| `get_departures` | `stop_id?` (default: nearest stop), `line_id?`, `low_floor_only?`, `limit?` | `stop_id`, `stop_name`, `departures` with `eta_min`, `delay_min`, `data_source`, `vehicle` |
| `match_boarded_vehicle` | `line_id?` (position from GPS) | `matched`, vehicle, `trip`; sets the side number for the ticket |
| `set_vehicle` | `side_number` (as spoken: "HG 935", "935") | vehicle + `trip`; sets the side number for the ticket |
| `vehicle_status` | `side_number?` (default: current vehicle) | position, remaining stops with ETA |
| `list_tickets` | `fare?` (`full` / `reduced`) | ticket catalog |
| `get_balance` | – | `balance_pln`, `balance_text`, default card, `speak_amount_aloud`, active tickets |
| `prepare_ticket` | `ticket_id?`, `side_number?`, `fare?` | `pending_action_id`, `confirmation_text`, `ticket_id`, `trip_min`, `covers_trip` (no money moves) |
| `confirm_pending_action` | `pending_action_id` | bought ticket, new balance |
| `cancel_pending_action` | – | what was cancelled |

`prepare_ticket` and `confirm_pending_action` must never happen in the same turn.

**Ticket length.** Without `ticket_id`, `prepare_ticket` picks the shortest ticket still valid 3 minutes
after the user leaves their last vehicle (`wallet.trip_minutes`):
on a vehicle of the planned route, its live ETA to that leg's stop plus the planned legs after it (transfers);
on any other vehicle, the ride to the end of its line; not on a running vehicle, the planned route.
With an explicit `ticket_id` that is too short, `covers_trip` is `false` and the agent warns the user.

### 5.2 WebSocket `/ws/voice`

Client → server:
```json
{"type": "context", "gps": true, "lat": 50.06, "lon": 19.98, "headphones": true, "lang": "pl"}
{"type": "audio_chunk", "data": "<base64>"}
{"type": "end_of_speech"}
{"type": "text", "text": "Jak dojadę na Rynek?"}
{"type": "stop"}
{"type": "extend_pending", "id": "<pending_action_id>"}
{"type": "listening", "id": "<pending_action_id>"}
```
- `audio_chunk`: iOS sends raw PCM16 16 kHz mono; Android sends AAC in an `.m4a` container (expo-audio can't record PCM there). `speech.py` detects the format.
- `context`: `gps: false` makes the backend forget the phone's position and plan from the venue.
- `text`: typed input, for tests and as an accessible alternative to speech.
- `extend_pending` ("Potrzebuję więcej czasu", WCAG 2.2.1) restarts the confirmation window of the pending purchase. It never confirms anything.
- `listening`: the phone finished reading the purchase question and opened the mic by itself (hands-free
  "tak"/"nie"). The silence timer restarts from that moment but keeps its retry count, so silence still
  ends in one retry and then a cancel. When a turn prepares a purchase, the server speaks only the
  `confirmation_text` (not the LLM's full answer) and the silence window starts after it has been read out.

Server → client:
```json
{"type": "session", "id": "a1b2c3d4"}
{"type": "state", "value": "listening | thinking | speaking | idle"}
{"type": "transcript", "text": "jak dojadę na rynek"}
{"type": "reply_text", "text": "Tramwaj 1 za 2 minuty..."}
{"type": "audio_chunk", "data": "<base64 mp3>"}
{"type": "haptic", "pattern": "confirm | warning | arrived"}
{"type": "ui", "component": "route_results | departures | ticket_confirm | trip_live", "data": {}}
{"type": "pending_confirmation", "id": "pa_1a2b3c", "timeout_s": 30, "data": {"...": "prepare_ticket result"}}
{"type": "pending_cancelled", "id": "pa_1a2b3c"}
{"type": "error", "message": "..."}
```

### 5.3 REST (debug + demo control)

| Endpoint | Purpose |
|---|---|
| `GET /health` | clock, and whether LLM / STT / TTS are configured |
| `GET /stops` · `GET /stops/{id}/departures` · `GET /vehicles/{side}` | raw mock data |
| `POST /route` · `GET /wallet` · `GET /tickets/catalog` | same data the tools return |
| `GET /tools/schemas` | tool definitions passed to Claude |
| `POST /agent/text` · `GET /sessions/{id}/log` | talk to the agent without the phone; action log of a session |
| `POST /demo/reset` (`offset_min`) | restart clock and wallet, clear fake GPS, reset open WebSocket sessions |
| `POST /demo/gps` (`side_number` or `lat`+`lon`) · `DELETE /demo/gps` | fake GPS for the stage |

## 6. Agent behaviour rules (in the system prompt and the rule-based brain)

1. Short answers, the most important information first: line, ETA, low-floor yes/no.
2. **Confirm with parameters**: ticket name, price (only if private), card, side number. Never a bare "confirm?".
3. **Silence is not consent**: after `timeout_s`, ask once more, then cancel.
4. **"Stop" / "anuluj" / "cancel"** cancels any pending action immediately.
5. **Repair only the unclear part**: an ambiguous destination gets one question listing the options.
6. **Privacy**: without headphones, ask before saying amounts aloud.
7. **Uncertainty**: say "według danych na żywo" vs "według rozkładu" based on `data_source`, e.g. when asked "czy się spóźni?".
8. Never invent departures or prices. If a tool fails, say so.
9. Answer in the language the user spoke.
10. **Ticket length**: let the backend pick a ticket that lasts the whole ride; warn if a ticket the user asked for is too short.

## 7. Demo script (≈90 s)

1. Ustawienia → Tryb demo → **Reset demo (start)**. Phone is mirrored and the screen reader is on.
2. "Jak dojadę na Rynek?" → route, ETA, low-floor.
3. "Kiedy następna czternastka?" → high-floor warning, then an offer to wait for the next low-floor one.
4. Tryb demo → **Wsiadam do HG935 (+12 min)** (fake GPS) → "Wsiadłem" →
   "Jesteś w linii 12, pojazd HG935. Kupić bilet 30-minutowy lub na 1 przejazd, normalny?"
   (no destination known, so the ticket covers the 27 min to the end of the line).
   Without GPS the user can also say the side number: "Jestem w HG 935".
5. "Tak" → confirmation with parameters → "Tak" → ticket.
6. Fallback: play the backup video.

## 8. Known issues

- "Kiedy następna dwunastka?" answers "Nie widzę teraz żadnych odjazdów": departures are looked up only at the
  nearest stop (Al. Pokoju), and tram 12 leaves from TAURON Arena Wieczysta. Don't ask it on stage.
- Ticket prices in the catalog are placeholders.
