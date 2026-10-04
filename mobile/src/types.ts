// Shapes of the backend payloads (see backend tools.py / mock_realtime.py / wallet.py).

export type Mode = "tram" | "bus" | "train";
export type LowFloor = "full" | "partial" | "none";

export type Vehicle = {
  side_number: string;
  model: string;
  low_floor: LowFloor;
  audio_stop_announcements: boolean;
  boarding_hint_pl: string;
  boarding_hint_en: string;
};

export type WalkLeg = {
  type: "walk";
  minutes: number;
  meters: number;
  to?: string;
  to_place?: string;
  instruction_pl: string;
  instruction_en: string;
  arrive: string;
};

export type RideLeg = {
  type: "ride";
  line_number: string;
  mode: Mode;
  headsign: string;
  from: string;
  to: string;
  departure: string;
  wait_min: number;
  ride_min: number;
  vehicle: Vehicle;
};

export type Leg = WalkLeg | RideLeg;

export type Itinerary = { total_min: number; arrival: string; legs: Leg[] };

export type RouteResult =
  | { status: "ok"; destination: string; best: Itinerary; alternatives: Itinerary[]; data_source: string }
  | { status: "ambiguous"; options: string[] }
  | { status: "not_found" }
  | { status: "no_route"; destination: string };

export type Departure = {
  line_id: string;
  line_number: string;
  mode: Mode;
  headsign: string;
  eta_min: number;
  departure_time: string;
  delay_min: number;
  data_source: string;
  vehicle: Vehicle;
};

export type DeparturesResult = { stop_id: string; stop_name: string; departures: Departure[] };

export type Stop = { id: string; name: string; lat: number; lon: number; modes: Mode[] };

export type TripStatus = {
  line_id: string;
  line_number: string;
  position: { lat: number; lon: number; previous_stop: string; next_stop: string; elapsed_min: number };
  remaining_stops: { stop_id: string; name: string; eta_min: number }[];
  delay_min: number;
  data_source: string;
  vehicle: Vehicle;
};

export type Ticket = {
  id: string;
  name_pl: string;
  name_en: string;
  price_pln: number;
  valid_min: number;
  zones: string;
  category: string;
  requires_vehicle_side_number: boolean;
};

export type PreparedTicket = {
  pending_action_id: string;
  confirmation_text: string;
  timeout_s: number;
  ticket: Ticket;
  side_number: string | null;
  payment_source: "balance" | "card";
  show_price: boolean;
  ticket_id: string;
  trip_min: number | null;
  covers_trip: boolean;
};

export type ActiveTicket = {
  ticket_id: string;
  name_pl: string;
  price_pln: number;
  vehicle: string | null;
  valid_from: string;
  valid_until: string;
  paid_with: string;
};

export type Wallet = {
  balance_pln: number;
  balance_text: string;
  default_card: string;
  speak_amount_aloud: boolean;
  active_tickets: ActiveTicket[];
};

// `ui` messages from /ws/voice (README: WebSocket /ws/voice).
export type UiPayload =
  | { component: "route_results"; data: RouteResult }
  | { component: "departures"; data: DeparturesResult }
  | { component: "ticket_confirm"; data: PreparedTicket }
  | { component: "trip_live"; data: TripStatus };

export type AgentState = "listening" | "thinking" | "speaking" | "idle";
