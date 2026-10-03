# FRONTEND.md — HearWeGoKrk mobile app (UI spec)

This describes the React Native (Expo) app in `mobile/` for **HearWeGoKrk**, a voice-first transit
assistant for blind people in Kraków. Keep it in sync with the code when screens change. The Trasa and Rozkłady screens use their own simple style, not the dense
style of typical transit apps: large type, one idea per row, plain words instead of icon-only chips,
and labelled values ("Odjazd 13:28", "Wysiądź: Rynek") instead of colour-coded pills.
Use the HearWeGoKrk name and the tokens below.

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
- Touch targets ≥ 48×48 dp. The talk button fills most of the Mów screen.
- **Never use colour alone**: a delay is red **and** says "opóźniony o 4 min".

## 3. Navigation

Bottom tabs (labels in Polish, icons + text):

| Tab | Route | Purpose |
|---|---|---|
| **Mów** | `/` | Voice home: big talk button, live transcript, last agent result |
| **Trasa** | `/route` | Route search + results + route detail |
| **Rozkłady** | `/departures` | Departures board for nearby / chosen stops |

Header on every tab: screen title on the left; on the right the **balance chip** (e.g. `20,14 zł`, hidden as
`•••• zł` without headphones until tapped), the profile/settings icon, and the help button (always last).

When the agent sends a `ui` message, store its data so the matching screen shows it. **Do not navigate automatically**: the user stays on the current screen and opens the result from the "Tekst rozmowy" panel or the tabs.

## 4. Shared components

Icons: plain outline icons from Lucide (`@react-native-vector-icons/lucide`) via the `Icon` / `IconText` components in `components/ui.tsx`. No emoji. Icons are decorative (hidden from screen readers); pair every colour or icon with words that say the same thing.

### `LineBox`
- A filled box with the line number in large type and the mode underneath ("14" / "tramwaj"). Decorative: the row's a11y label covers it.

### `LowFloorNote`
- `accessibility` icon + "niskopodłogowy" / "częściowo niskopodłogowy" in green, `triangle-alert` icon + "wysokie stopnie" in red.

### `LiveIndicator`
- Text `"● na żywo"` (green, or red when delayed), or muted `"według rozkładu"`. Maps to `data_source` from the backend.

### `TalkButton`
- A large rounded panel in the accent colour that fills the space it is given. States: idle / listening (pulsing border) / thinking (spinner) (while the reply plays it looks idle: "Mów").
- Haptics: `impactAsync(Medium)` on press, `notificationAsync(Success)` when a reply starts.
- a11y: role button, label `"Mów do asystenta"`, hint `"Przytrzymaj i mów, albo stuknij, aby zacząć"` (`"Stuknij, aby wysłać"` while listening).

### `TicketFab`
- A floating yellow cart button, bottom-right, on the route screens. It sends "kup bilet" to the agent: the backend
  picks a ticket that lasts the whole ride and the purchase continues in the 5.7 sheet. An optional black price
  pill to its left (`"Kup bilet · 6,00 zł"`) shows only with headphones and when a price is passed (no screen passes one yet).

## 5. Screens

### 5.1 Voice home (`/`)
- The `TalkButton` fills most of the screen (a large rounded panel), so a blind user can hit it without aiming.
- No text input: the app is used by speaking.
- Under it, small buttons: **"Tekst rozmowy"** (`message-square-text` icon) and, once there is a reply, **"Powtórz"** (`rotate-ccw` icon) (replays the last audio).
- "Tekst rozmowy" opens a full-screen panel: the user's transcript, the agent's reply in large type, the last result card (tap opens the full screen), and, before the first question, 3 example phrases ("Jak dojadę na Rynek?", "Kiedy następna czternastka?", "Kup bilet") for discoverability.
- The connection warning and ticket notices stay on the main screen, above the button.

### 5.2 Route search (`/route`)
- Heading "Dokąd jedziesz?", with the origin under it ("Z: Twoja lokalizacja · odjazd teraz"). The backend plans from the user's position only.
- One large destination input and a "Szukaj trasy" button.
- "Szybki wybór": one-tap buttons for known destinations (Rynek, AGH, Dworzec Główny, Kampus UJ).
- A low-floor option card with a switch, and a note that the data is live and voice works too.

### 5.3 Route results (`/route/results`)
- Header "Trasy do" + destination in large type.
- One `RouteCard` per itinerary, titled "Polecana trasa" / "Inna trasa N":
  - Top: "za 5 min" in large type + "odjazd 13:28" on the left; total minutes + "przyjazd 14:05" on the right.
  - Then the legs as plain lines: "Pieszo 4 min" (`footprints` icon), "Tramwaj 14, kierunek Bronowice" (mode icon) + `LowFloorNote`.
  - Footer: `LiveIndicator` and "Szczegóły ›".
- **One accessible element per card**. Example label:
  `"Polecana trasa. Odjazd za 5 minut. Autobus 128, potem 172. Dojście 4 minuty. Odjazd 13:28, przyjazd 14:05. Razem 41 minut. Wszystkie pojazdy niskopodłogowe."`
- A "Zmień cel podróży" button at the bottom. Floating `TicketFab`.

### 5.4 Route detail (`/route/[id]`)
- The route summary card at the top, then the route as numbered step cards ("Krok 1", "Krok 2", …):
  - Walk step: "Idź 800 m", the spoken `instruction_pl`, the time it takes, and when you arrive.
  - Ride step: `LineBox` + "Wsiądź: tramwaj 14" + headsign; "Przystanek" and "Odjazd" rows; a vehicle box (side number in large type, model, `LowFloorNote`, `boarding_hint_pl`); "Wysiądź" and "O godzinie" rows.
  - Goal card: `map-pin` icon + destination, then "Przyjazd".
- Floating `TicketFab`.

### 5.5 Departures board (`/departures`)
- Header "Przystanek" + stop name in large type.
- One input "Zmień przystanek lub wpisz nr linii": a name lists matching stops, digits filter to that line. An active line filter shows "Tylko linia 14" with a "Pokaż wszystkie" button.
- A segmented control: Wszystkie / Tramwaje / Autobusy.
- "Najbliższe odjazdy" (refreshed every 30 s; "Wstrzymaj odświeżanie" pauses it): per row, `LineBox` · "→ headsign" + `LowFloorNote` (+ "Opóźniony o 4 min (planowo 15:54)") · on the right "2 min" in large type, the clock time (red if delayed, green if live) and `LiveIndicator`.
- a11y label per row: `"Autobus 179 w kierunku Dworzec Główny, za 2 minuty, o 15:58, na żywo, niskopodłogowy"`.

### 5.6 Tickets — removed
- No tickets screen or tab. Buying is voice-only ("kup bilet", or the cart `TicketFab` on route screens) and always ends in the 5.7 sheet.

### 5.7 Ticket confirmation (bottom sheet) — HearWeGoKrk addition
- Opened by the `pending_confirmation` message, closed by `pending_cancelled` or the `confirm` haptic.
- Not a `Modal`: an overlay at the bottom, so the big Mów button behind it stays reachable. Android back = Anuluj.
- Shows the parameters in large type: ticket name (its length is picked by the backend for the whole ride),
  **vehicle side number**, price (hidden behind "Pokaż kwotę" unless `show_price`), payment (balance or card).
- Hands-free answer: after the question has been read out, the phone opens the mic by itself, sends `listening`,
  and stops recording when the user goes quiet. While the question is read: **"Przerwij i odpowiedz"**;
  while listening: **"Wyślij odpowiedź"**. A status line says what is happening ("Słucham — powiedz „tak” albo „nie”").
- Countdown matching `timeout_s`, frozen while the question is read or the answer checked; a vibration at 10 s and 5 s
  (not spoken: it would land in the open mic). On silence the server asks once more, then cancels ("Nie kupiono biletu").
- Buttons: **Potwierdź** (ticket yellow, sends "tak"), **Anuluj** (outlined), and **"Potrzebuję więcej czasu"**
  (`extend_pending`, WCAG 2.2.1; it never confirms).

### 5.8 Trip in progress — HearWeGoKrk addition
- Huge text: line + side number ("12 · HG935"), the next stop, and "Wysiadasz za 2 przystanki".
- A list of the remaining stops with ETAs (from `vehicle_status`).
- A haptic pattern + announcement one stop before the destination.

## 6. Agent → UI payloads

The backend sends a `ui` message on `/ws/voice` right after a tool result that has a screen:

```json
{ "type": "ui", "component": "route_results", "data": { /* plan_route result */ } }
```

| `component` | Screen | `data` comes from |
|---|---|---|
| `route_results` | 5.3 | `plan_route` (`best` + `alternatives`) |
| `departures` | 5.5 | `get_departures` |
| `ticket_confirm` | 5.7 | `prepare_ticket` |
| `trip_live` | 5.8 | `match_boarded_vehicle`, `set_vehicle`, `vehicle_status`, and the trip monitor (every ~10 s) |

`AgentContext` stores the latest `data` per component (`ui`) and the last result (`lastUi`, shown in "Tekst rozmowy").
Unknown components are ignored, never crashed on.

## 7. Accessibility checklist (definition of done)

- [ ] The whole S1 → S6 → S7 → S11 journey works with **TalkBack/VoiceOver turned on**.
- [ ] Each card or row is one focusable element with a full sentence label (examples above).
- [ ] Focus order: header → main content → FAB → tabs.
- [ ] Delays are announced once, not on every refresh.
- [ ] Text survives 200% font scale without clipping.
- [ ] No information is conveyed by colour only.
- [ ] Every action that costs money goes through the 5.7 sheet.

### WCAG 2.2 (target: level AA)

The app follows [WCAG 2.2](https://www.w3.org/TR/WCAG22/), applied to a native app. Where each criterion lives:

| Criterion | How the app meets it | Where |
|---|---|---|
| 1.3.4 Orientation (AA) | Portrait and landscape both work; orientation is not locked. | `app.json` |
| 1.4.3 Contrast (Minimum) (AA) | Text ≥ 4.5:1. Button greens/purples were darkened so white labels pass (5.0:1, 5.1:1). | `theme.ts` |
| 1.4.4 Resize Text (AA) | System font scaling stays on; layouts wrap at 200%. | all screens |
| 1.4.11 Non-text Contrast (AA) | Input outlines and the switch "off" track use `colors.border` (≥ 4.4:1); the selected segment is ≥ 3:1 against its track. | `ui.tsx` (`inputOutline`, `switchColors`) |
| 2.2.1 Timing Adjustable (A) | The purchase confirmation has a "Potrzebuję więcej czasu" button (`extend_pending` → fresh window on the server). Silence still never confirms. | `money.tsx`, `voice_ws.py` |
| 2.2.2 Pause, Stop, Hide (A) | The auto-refreshing departures list can be paused. | `departures.tsx` |
| 2.3.3 Animation from Interactions (AAA) | With the phone's "remove animations" setting on, the talk button's pulse and the modal slide-ins are turned off. | `a11y.ts` (`useReducedMotion`) |
| 2.5.2 Pointer Cancellation (A) | Recording starts on touch-down, but sliding the finger off the button before release cancels it, and an "Anuluj" button cancels a tap-started recording. Nothing is sent. | `TalkButton.tsx`, `cancelListening` |
| 2.5.7 Dragging Movements (AA, new) | No feature needs dragging (the ticket carousel is gone). | — |
| 2.5.8 Target Size (Minimum) (AA, new) | Every control is ≥ 48×48 dp (WCAG asks for 24). The talk button fills the screen. | `MIN_TOUCH` |
| 3.2.6 Consistent Help (A, new) | A help button (`circle-help`) is always the last item in the header, on every screen, and opens the Pomoc screen. | `header.tsx`, `app/help.tsx` |
| 3.3.4 Error Prevention (Financial) (AA) | Every purchase is confirmed in the 5.7 sheet or by an explicit spoken "tak". | `money.tsx` |
| 3.3.7 Redundant Entry (A, new) | Trasa keeps the last destination and route; Rozkłady keeps the asked stop. | `route/index.tsx`, `departures.tsx` |
| 3.3.8 Accessible Authentication (AA, new) | No login or password: nothing to remember or transcribe. | — |
| 4.1.2 Name, Role, Value (A) | Every control has a Polish label and role; icons are hidden from screen readers. | all screens |
| 4.1.3 Status Messages (AA) | Notices, connection loss and errors are announced without moving focus. | `a11y.ts` (`useAnnounce`) |

Not covered yet: 2.4.11 Focus Not Obscured and 2.4.7 Focus Visible with a hardware keyboard (not tested), 3.1.1/3.1.2 language of content for screen readers when replies are in English.
