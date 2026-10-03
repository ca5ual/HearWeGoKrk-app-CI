# HearWeGoKrk 🎧🚋

Voice-first public transport assistant for blind and visually impaired people in Kraków.
One big button (Shazam-style): plan a route, hear live departures, check whether the vehicle
is low-floor, buy a ticket with the **vehicle side number filled in automatically**, and get
told when to get off.

HackYeah 2026 · Smart City category (Bank Pekao).

---

## 1. Architecture

```
React Native (Expo)  ──audio + GPS──▶  FastAPI  ──▶  Parakeet V3 (speech → text)
        ▲                                  │
        │                                  ▼
        │                       LLM agent with tool calling
        │                                  │
        │                    tools ──▶ mock_realtime.py (or live GTFS-RT / TTSS)
        │                                  │         wallet / tickets (mock)
        │                                  ▼
        └──────audio + text + haptic──  ElevenLabs (text → speech)
```

- **Parakeet V3** is speech-to-text only. The "agent" is the LLM that calls tools.
- **ElevenLabs** streams the spoken reply in Polish or English.
- Every agent reply is sent as **audio + text** (text shown on screen for a sighted companion, and available for "powtórz / repeat").

## 2. Repo layout (suggested)

```
backend/
  app.py              FastAPI app, routers
  voice_ws.py         WebSocket: audio in → STT → agent → TTS → audio out
  agent.py            LLM loop, system prompt, tool registry, conversation state
  tools.py            thin wrappers around mock_realtime + wallet
  mock/               ← this folder (JSON files + mock_realtime.py)
mobile/
  App.tsx             big button screen
  audio.ts            record / play / stream
  location.ts         GPS (+ demo GPS override)
```

## 3. Mock data (this folder)

| File | Contents |
|---|---|
| `stops.json` | Real Kraków stop names, approx. coordinates, step-free / tactile / voice-board flags |
| `lines_and_vehicles.json` | Tram 1, tram 14, bus 152; vehicles with side number, model, `low_floor` (full/partial/none) |
| `routes.json` | Route templates from the venue, destination aliases, ambiguous aliases ("rondo") |
| `account_and_tickets.json` | Demo persona, wallet, mock card, ticket catalog, confirmation templates |
| `demo_scenarios.json` | 12-case golden set: typical / hard / high-risk |
| `mock_realtime.py` | Simulator: departures count down, vehicles move, delays appear |

Smoke test: `python mock_realtime.py`

**Before the demo, call `reset_clock()`**: the first tram 14 is then the high-floor HY854 running 3 min late,
and the next one (RZ612) is low-floor. That is scenario S5.

⚠️ Ticket prices are placeholders (check ztp.krakow.pl). Side numbers are illustrative.

## 4. Contracts (agree on these FIRST, then work in parallel)

### 4.1 Agent tools (backend implements, agent calls)

| Tool | Args | Returns |
|---|---|---|
| `plan_route` | `destination: str, prefer_low_floor: bool=true` | `status` ok / ambiguous / not_found / no_route, `best`, `alternatives`, `data_source` |
| `get_departures` | `stop_id: str, line_id?: str, low_floor_only?: bool` | list of departures with `eta_min`, `delay_min`, `vehicle` |
| `match_boarded_vehicle` | `lat, lon, line_id?` | matched vehicle or null |
| `vehicle_status` | `side_number` | position, remaining stops with ETA |
| `get_balance` | – | `balance_pln`, default card label |
| `prepare_ticket` | `ticket_id, side_number` | `pending_action_id` + confirmation text (no money moves) |
| `confirm_pending_action` | `pending_action_id` | ticket |
| `cancel_pending_action` | – | what was cancelled |

`prepare_ticket` and `confirm_pending_action` must never happen in the same turn.

### 4.2 WebSocket `/ws/voice`

Client → server:
```json
{"type": "audio_chunk", "data": "<base64 pcm16 16kHz>"}
{"type": "end_of_speech"}
{"type": "context", "lat": 50.06, "lon": 19.98, "headphones": true, "lang": "pl"}
{"type": "stop"}
```
Server → client:
```json
{"type": "state", "value": "listening | thinking | speaking | idle"}
{"type": "transcript", "text": "jak dojadę na rynek"}
{"type": "reply_text", "text": "Tramwaj 1 za 2 minuty..."}
{"type": "audio_chunk", "data": "<base64 mp3/pcm>"}
{"type": "haptic", "pattern": "confirm | warning | arrived"}
{"type": "pending_confirmation", "id": "pa_1", "timeout_s": 8}
```

### 4.3 REST (debug + demo control)

`GET /stops/{id}/departures` · `GET /vehicles/{side}` · `POST /route` · `GET /wallet` · `POST /demo/reset` · `POST /demo/gps` (fake GPS for the stage)

## 5. Agent behaviour rules (put into the system prompt)

1. Short answers, the most important information first: line, ETA, low-floor yes/no.
2. **Confirm with parameters**: ticket name, price (only if private), card, side number. Never a bare "confirm?".
3. **Silence is not consent**: after `timeout_s`, ask once more, then cancel.
4. **"Stop" / "anuluj" / "cancel"** cancels any pending action immediately.
5. **Repair only the unclear part**: an ambiguous destination gets one question listing the options.
6. **Privacy**: without headphones, ask before saying amounts aloud.
7. **Uncertainty**: say "według danych na żywo" vs "według rozkładu" based on `data_source`.
8. Never invent departures or prices. If a tool fails, say so.
9. Answer in the language the user spoke.

## 6. Work split (3 people)

### 🎙️ Person A: Voice & Agent
- Run Parakeet V3 (NeMo on GPU, or ONNX on CPU) and measure latency on Polish.
- Integrate ElevenLabs streaming TTS and pick a Polish voice.
- Build the LLM loop with tool calling (`agent.py`): system prompt (section 5), conversation state, pending action.
- Run the golden set from `demo_scenarios.json` in text mode first, then by voice.
- **Definition of done:** S1–S12 pass in text mode; S1, S5 and S7 pass end-to-end by voice.

### 🛠️ Person B: Backend & Data
- FastAPI skeleton, `/ws/voice` plumbing (with Person A), REST endpoints from 4.3.
- Wrap `mock_realtime.py` and the wallet into the tools in 4.1, including the pending-action state machine (prepare → confirm/cancel/timeout).
- Demo controls: `/demo/reset`, `/demo/gps`.
- Stretch: live adapter for ZTP GTFS-RT or TTSS behind the same `get_departures`, with the mock as fallback.
- **Definition of done:** every tool returns valid JSON for all scenarios; the backend runs on one laptop with no internet except the LLM and TTS APIs.

### 📱 Person C: Mobile App & Accessibility
- Expo app with one big button: press to talk, haptic for listening / thinking / done.
- Recording and streaming audio over the WebSocket, then playback.
- Send GPS + headphones state as `context`, plus a hidden demo toggle that sends fake GPS.
- Screen: large high-contrast transcript and reply text (companion view), a "Powtórz" button, and a trip-in-progress view.
- Accessibility pass: `accessibilityLabel` and roles everywhere; test with TalkBack/VoiceOver turned ON.
- **Definition of done:** the full S1 → S6 → S7 → S11 journey works on a real phone with the screen reader enabled.

### Shared: Pitch (Julia leads the presentation)
- Everyone gives Julia one screenshot or clip of their part by the feature freeze.
- Record the **backup video** of the real ride from the nearest stop.
- Rehearse the demo script at least twice on the stage setup (headset mic, phone mirroring).

## 7. Timeline (24 h)

| Hour | Milestone |
|---|---|
| H+2 | Contracts in section 4 agreed, repo skeleton pushed |
| H+8 | Text-only loop: typed question → agent → tools → text answer |
| H+12 | Voice end-to-end on a laptop |
| H+16 | Mobile app talks to the backend over the WebSocket |
| H+19 | **Feature freeze.** Bugs only |
| H+20 | Backup video recorded, slides final |
| H+22 | Two full rehearsals, `reset_clock()` routine checked |

## 8. Demo script (≈90 s)

1. `POST /demo/reset`. Phone is mirrored and the screen reader is on.
2. "Jak dojadę na Rynek?" → route, ETA, low-floor.
3. "Kiedy następna czternastka?" → high-floor warning, then an offer to wait.
4. Fake GPS onto RZ612 → "Jesteś w tramwaju 14, pojazd RZ612. Kupić bilet?"
5. "Tak" → confirmation with parameters → "Tak" → ticket.
6. Fallback: play the backup video.
