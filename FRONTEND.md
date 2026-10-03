# FRONTEND.md — HearWeGoKrk mobile app (instructions for the coding agent)

You are building the React Native (Expo) app for **HearWeGoKrk**, a voice-first transit assistant
for blind people in Kraków. The screens are **inspired by the layout of Jakdojade**, a popular
Polish transit app. Copy the information architecture, not the brand: no Jakdojade name,
logo, colours one-to-one, or ads. Use the HearWeGoKrk name and the tokens below.

The voice agent is the primary interface. Every screen below is also a **companion view**:
the agent's tool results are rendered here, so a sighted companion can read along and the
user can return to the information ("wejście głosem, wyjście w formie, do której można wrócić").

Read `README.md` first for the WebSocket protocol and tool contracts.

---

## 1. Stack

- Expo (managed) + TypeScript + `expo-router` (tabs).
- `expo-audio` (recording/playback), `expo-location`, `expo-haptics`.
- No UI kit is needed. Write plain components with `StyleSheet`.
- State: React context (`AgentContext`) holding the last `ui` payload, the transcript and the connection state.

## 2. Design tokens (dark, high contrast)

```ts
export const colors = {
  bg: "#0E0E10",          // app background
  surface: "#1C1C1F",     // cards
  surfaceAlt: "#26262A",  // chips, inputs, pressed state
  text: "#FFFFFF",
  textMuted: "#A6A6AD",   // min. 4.5:1 on surface — verify
  depart: "#12A36F",      // departure time chip (green)
  arrive: "#1B8FD6",      // arrival time chip (blue)
  live: "#2BD69B",        // live data, on time
  delay: "#FF5C6C",       // delayed / cancelled
  accent: "#7C5CFF",      // HearWeGoKrk brand accent (talk button, active tab)
  ticket: "#FFC94D",      // ticket / cart actions
};
export const radius = { card: 20, chip: 12, pill: 999 };
export const space = (n: number) => n * 4;
```

- Font: one bold geometric sans (e.g. Manrope or Inter via `expo-font`). Weights: 800 for big numbers, 700 for titles, 500 for body.
- Must respect system font scaling (`allowFontScaling` stays on). Layouts must survive 200% text.
- Touch targets ≥ 48×48 dp. The talk button is ≥ 160 dp.
- **Never use colour alone**: a delay is red **and** says "opóźniony o 4 min".

## 3. Navigation

Bottom tabs (labels in Polish, icons + text):

| Tab | Route | Purpose |
|---|---|---|
| **Mów** | `/` | Voice home: big talk button, live transcript, last agent result |
| **Trasa** | `/route` | Route search + results + route detail |
| **Rozkłady** | `/departures` | Departures board for nearby / chosen stops |
| **Bilety** | `/tickets` | Ticket shop + "Twoje bilety" |

Header on every tab: screen title on the left, **balance chip** (e.g. `20,14 zł`) and a profile icon on the right.

When the agent sends a `ui` message, navigate to the matching screen and render its data (section 6).

## 4. Shared components

### `LineBadge`
- Props: `{ mode: "tram" | "bus" | "train", number: string, lowFloor?: "full" | "partial" | "none" }`
- Look: mode icon + rounded outlined box with the line number (bold). If `lowFloor` is "full" or "partial", show a small ♿ marker; if "none", show a small warning marker "stopnie".
- a11y label: `"tramwaj 14, niskopodłogowy"` / `"autobus 152"`.

### `TimeChip`
- Props: `{ time: "13:28", kind: "depart" | "arrive" | "planned" }`
- A filled pill (green for depart, blue for arrive). `planned` = struck-through grey text, used next to a delayed time.

### `WalkSegment`
- Walking icon + `"4 min"`. a11y: `"dojście 4 minuty"`.

### `LiveIndicator`
- A small "((•))" broadcast icon. Green = live and on time, red = live and delayed, hidden = timetable only.
- a11y: `"dane na żywo"` or `"według rozkładu"`. This maps to `data_source` from the backend.

### `CountdownBig`
- `"Odjazd za:"` small label above a huge number + `"min"`. Numbers below 10 are zero-padded ("05").
- Updates every 30 s. Do **not** put it in an `accessibilityLiveRegion` (too chatty). Announce only changes ≥ 2 min or a new delay, via `AccessibilityInfo.announceForAccessibility`.

### `TalkButton`
- A big circle in the accent colour, centred. States: idle / listening (pulsing ring) / thinking (spinner) / speaking (waveform).
- Haptics: `impactAsync(Medium)` on press, `notificationAsync(Success)` when a reply starts.
- a11y: role button, label `"Mów do asystenta"`, hint `"Przytrzymaj i mów"`.

### `TicketFab`
- A floating yellow cart button, bottom-right, with an optional black pill to its left: `"Kup bilet · 4,00 zł"`.

## 5. Screens

### 5.1 Voice home (`/`)
- The centre of the screen is the `TalkButton`.
- Above it: the agent's last reply text, in large type.
- Below it: the user's transcript in muted text.
- A "Powtórz" button replays the last audio reply.
- Below that: a compact card with the last result (e.g. the best route), which opens the full screen when tapped.
- An empty state lists 3 example phrases ("Jak dojadę na Rynek?", "Kiedy następna czternastka?", "Kup bilet"). This solves voice discoverability.

### 5.2 Route search (`/route`) — reference: Jakdojade screenshot 2
- Two stacked inputs: origin (default "Moja lokalizacja") and destination, with a swap button.
- A time selector pill ("15:55 ▾") and an "Opcje" pill (toggles: prefer low-floor, max walk).
- A footer pill showing live-data coverage (e.g. "((•)) dane na żywo").
- A big green primary button: "Pokaż trasy →".

### 5.3 Route results (`/route/results`) — reference: screenshots 1 & 7
- Header: origin → destination with a vertical dot-line connector, and a filter button.
- A list of `RouteCard`s, one per itinerary:
  - Left: `CountdownBig` + `LiveIndicator`.
  - Right, row 1: the sequence of `LineBadge`s, total minutes at the far right.
  - Right, row 2: `WalkSegment` → `TimeChip(depart)` → ride minutes → `TimeChip(arrive)` → optional final walk.
- **One accessible element per card**. Example label:
  `"Odjazd za 5 minut. Autobus 128, potem 172, potem 168. Dojście 4 minuty. Odjazd 13:28, przyjazd 14:05. Razem 41 minut. Wszystkie pojazdy niskopodłogowe."`
- Floating `TicketFab`.

### 5.4 Route detail (`/route/[id]`) — reference: screenshots 5 & 6
- Sticky summary at the top (same as the `RouteCard` row).
- A vertical timeline. The left column shows times, the rail is coloured per leg (green for the first ride, blue for the next), and the right column shows content:
  - Origin row: `"● 15:56  Stanisława Lema 7"`.
  - Walk row: icon, "Idź 800 m", minutes on the right. Show the spoken `instruction_pl` underneath, smaller.
  - Ride boarding row: the planned time struck through and the real time in red if delayed; the stop name in bold; a red text line "Odjazd opóźniony o 4 min"; `LineBadge` → headsign; ride minutes; "Odjazdy co ok. 5 min"; an expandable "4 przystanki ▾".
  - **HearWeGoKrk addition:** a vehicle row with the side number in large type, the model, and the low-floor status + `boarding_hint_pl` (e.g. "Niska podłoga tylko w środkowym członie — wsiadaj środkowymi drzwiami").
  - Transfer row: "Poczekaj na przesiadkę · 10 min".
  - Destination row.
- Bottom: a "⋮" menu button on the left; `TicketFab` with the price on the right.
- No ad banners.

### 5.5 Departures board (`/departures`) — reference: screenshot 4
- A search input "Wyszukaj linię lub przystanek…" and filter chips: Tramwaje / Autobusy.
- A "Odjazdy" section; for each stop: the stop name + chevron, then rows of
  `LineBadge` → headsign (truncated) · `LiveIndicator` · "za 2 min" · clock time (red if delayed, green if live and on time).
- a11y label per row: `"Autobus 179 w kierunku Dworzec Główny, za 2 minuty, o 15:58, na żywo, niskopodłogowy"`.

### 5.6 Tickets (`/tickets`) — reference: screenshot 3
- Segmented tabs: **Sklep** | **Twoje bilety**.
- A Ulgowe / Normalne toggle (a pill segmented control).
- Section "Czasowe": horizontal carousel of `TicketCard`s. Each card has a coloured header strip ("ULGOWY" / "NORMALNY"), the operator line "ZTP w Krakowie", "Strefa: I+II+III", a huge duration number ("15" / "30") + "minut" / "minut lub 1 przejazd", and the price at the bottom ("2,00 zł").
- Data: `ticket_catalog` from `account_and_tickets.json`.
- A carousel is hard with a screen reader. Also expose the list as a plain vertical list when `AccessibilityInfo.isScreenReaderEnabled()` is true.

### 5.7 Ticket confirmation (modal) — HearWeGoKrk addition
- Opened by the `pending_confirmation` message.
- Shows the parameters in large type: ticket name, price (hidden behind "Pokaż kwotę" if `headphones=false`), card label, **vehicle side number**.
- Two full-width buttons: **Potwierdź** (ticket yellow) and **Anuluj** (outlined). A visible countdown matching `timeout_s`; when it ends, the modal closes with "Nie kupiono biletu".

### 5.8 Trip in progress — HearWeGoKrk addition
- Huge text: line + side number ("14 · RZ612"), the next stop, and "Wysiadasz za 2 przystanki".
- A list of the remaining stops with ETAs (from `vehicle_status`).
- A haptic pattern + announcement one stop before the destination.

## 6. Agent → UI payloads

Add this message type to `/ws/voice` (backend sends it right after the tool result):

```json
{ "type": "ui", "component": "route_results", "data": { /* plan_route result */ } }
```

| `component` | Screen | `data` comes from |
|---|---|---|
| `route_results` | 5.3 | `plan_route` (`best` + `alternatives`) |
| `route_detail` | 5.4 | one itinerary from `plan_route` |
| `departures` | 5.5 | `get_departures` |
| `ticket_shop` | 5.6 | ticket catalog |
| `ticket_confirm` | 5.7 | `prepare_ticket` |
| `trip_live` | 5.8 | `vehicle_status` |

Write a single `renderAgentUI(payload)` switch. Unknown components are ignored, never crashed on.

## 7. Accessibility checklist (definition of done)

- [ ] The whole S1 → S6 → S7 → S11 journey works with **TalkBack/VoiceOver turned on**.
- [ ] Each card or row is one focusable element with a full sentence label (examples above).
- [ ] Focus order: header → main content → FAB → tabs.
- [ ] Delays are announced once, not on every refresh.
- [ ] Text survives 200% font scale without clipping.
- [ ] No information is conveyed by colour only.
- [ ] Every action that costs money goes through the 5.7 modal.

## 8. Build order (hackathon)

1. Tokens + `LineBadge`, `TimeChip`, `CountdownBig` (with static mock props).
2. Screen 5.3 route results rendering `plan_route` JSON from the mock.
3. Voice home 5.1 with the WebSocket hooked up.
4. Route detail 5.4 with the vehicle row.
5. Confirmation modal 5.7 + trip-in-progress view 5.8 (needed for the demo).
6. Departures board 5.5, tickets 5.6 (nice to have).
