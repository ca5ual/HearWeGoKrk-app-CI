// RouteCard (5.3), ItineraryTimeline (5.4), DepartureRow (5.5), TripView (5.8).
import React from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { inMinutes, isLive, lowFloorLabel, minusMinutes, minutesPl, modeName, stopsPl } from "../format";
import { colors, radius, space } from "../theme";
import type { Departure, Itinerary, RideLeg, TripStatus } from "../types";
import { CountdownBig, LineBadge, LiveIndicator, TimeChip, WalkSegment } from "./transit";
import { Card, T } from "./ui";

const rides = (it: Itinerary) => it.legs.filter((l): l is RideLeg => l.type === "ride");

/** Minutes from now until the first vehicle leaves (walk to the stop + wait). */
export function minutesToDeparture(it: Itinerary): number {
  let m = 0;
  for (const leg of it.legs) {
    if (leg.type === "walk") m += leg.minutes;
    else return m + leg.wait_min;
  }
  return m;
}

const plus = (hhmm: string, n: number) => minusMinutes(hhmm, -n);

export function itineraryLabel(it: Itinerary): string {
  const r = rides(it);
  const first = r[0];
  const lines = r.map((x, i) => (i === 0 ? `${modeName(x.mode)} ${x.line_number}` : `potem ${x.line_number}`));
  const walk = it.legs.reduce((n, l) => n + (l.type === "walk" ? l.minutes : 0), 0);
  const lf = r.every((x) => x.vehicle.low_floor === "full")
    ? "Wszystkie pojazdy niskopodłogowe."
    : r.some((x) => x.vehicle.low_floor === "none")
      ? "Uwaga, pojazd z wysokimi stopniami."
      : "Częściowo niskopodłogowe.";
  const dep = minutesToDeparture(it);
  return [
    `Odjazd ${inMinutes(dep)}.`,
    lines.join(", ") + ".",
    `Dojście ${walk} ${minutesPl(walk)}.`,
    first ? `Odjazd ${first.departure}, przyjazd ${it.arrival}.` : `Przyjazd ${it.arrival}.`,
    `Razem ${it.total_min} ${minutesPl(it.total_min)}.`,
    lf,
  ].join(" ");
}

export function RouteCard({ it, dataSource, onPress }: { it: Itinerary; dataSource?: string; onPress?: () => void }) {
  const r = rides(it);
  const firstWalk = it.legs[0]?.type === "walk" ? it.legs[0].minutes : 0;
  const lastLeg = it.legs[it.legs.length - 1];
  return (
    <Pressable
      onPress={onPress}
      accessible
      accessibilityRole="button"
      accessibilityLabel={itineraryLabel(it)}
      accessibilityHint="Otwiera szczegóły trasy"
    >
      <Card style={styles.routeCard}>
        <View style={{ alignItems: "center", gap: space(1) }}>
          <CountdownBig minutes={minutesToDeparture(it)} />
          <LiveIndicator dataSource={dataSource} />
        </View>
        <View style={{ flex: 1, gap: space(2) }}>
          <View style={styles.rowWrap}>
            {r.map((x, i) => (
              <LineBadge key={i} mode={x.mode} number={x.line_number} lowFloor={x.vehicle.low_floor} />
            ))}
            <T variant="title" style={{ marginLeft: "auto" }}>{it.total_min} min</T>
          </View>
          <View style={styles.rowWrap}>
            {firstWalk ? <WalkSegment minutes={firstWalk} /> : null}
            {r[0] ? <TimeChip time={r[0].departure} kind="depart" /> : null}
            {r[0] ? <T variant="muted">{r.reduce((n, x) => n + x.ride_min, 0)} min</T> : null}
            <TimeChip time={it.arrival} kind="arrive" />
            {lastLeg?.type === "walk" && it.legs.length > 1 ? <WalkSegment minutes={lastLeg.minutes} /> : null}
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export function ItineraryTimeline({ it }: { it: Itinerary }) {
  let rideIdx = 0;
  return (
    <View style={{ gap: space(1) }}>
      {it.legs.map((leg, i) => {
        if (leg.type === "walk") {
          return (
            <TimelineRow key={i} time={leg.arrive} rail={colors.textMuted} dashed>
              <View accessible accessibilityLabel={`Idź ${leg.meters} metrów, ${leg.minutes} ${minutesPl(leg.minutes)}. ${leg.instruction_pl}`}>
                <View style={styles.between}>
                  <T variant="title" size={17}>🚶 Idź {leg.meters} m</T>
                  <T variant="muted">{leg.minutes} min</T>
                </View>
                <T variant="muted">{leg.instruction_pl}</T>
              </View>
            </TimelineRow>
          );
        }
        const rail = rideIdx++ === 0 ? colors.depart : colors.arrive;
        const v = leg.vehicle;
        return (
          <TimelineRow key={i} time={leg.departure} rail={rail}>
            <View style={{ gap: space(2) }}>
              <View
                accessible
                accessibilityLabel={`${leg.from}. ${modeName(leg.mode)} ${leg.line_number} w kierunku ${leg.headsign}, odjazd ${leg.departure}, jazda ${leg.ride_min} ${minutesPl(leg.ride_min)}, do przystanku ${leg.to}.`}
                style={{ gap: space(1) }}
              >
                <T variant="title">{leg.from}</T>
                <View style={styles.rowWrap}>
                  <LineBadge mode={leg.mode} number={leg.line_number} lowFloor={v.low_floor} />
                  <T variant="muted">→ {leg.headsign}</T>
                </View>
                <T variant="muted">{leg.ride_min} min jazdy, do: {leg.to}</T>
              </View>
              <View
                style={styles.vehicle}
                accessible
                accessibilityLabel={`Pojazd ${v.side_number.split("").join(" ")}, ${v.model}, ${lowFloorLabel(v.low_floor)}. ${v.boarding_hint_pl}`}
              >
                <T variant="number" size={30}>{v.side_number}</T>
                <T variant="muted">{v.model}</T>
                <T color={v.low_floor === "none" ? colors.delay : colors.live}>
                  {v.low_floor === "none" ? "⚠ " : "♿ "}
                  {lowFloorLabel(v.low_floor)}
                </T>
                <T>{v.boarding_hint_pl}</T>
              </View>
              <View style={styles.rowWrap}>
                <TimeChip time={plus(leg.departure, leg.ride_min)} kind="arrive" />
                <T variant="title" size={16}>{leg.to}</T>
              </View>
            </View>
          </TimelineRow>
        );
      })}
      <TimelineRow time={it.arrival} rail="transparent">
        <T variant="title" accessibilityLabel={`Cel, przyjazd ${it.arrival}`}>📍 Cel</T>
      </TimelineRow>
    </View>
  );
}

function TimelineRow({ time, rail, dashed, children }: { time: string; rail: string; dashed?: boolean; children: React.ReactNode }) {
  return (
    <View style={styles.tlRow}>
      <T variant="title" size={15} style={styles.tlTime} importantForAccessibility="no">{time}</T>
      <View style={[styles.rail, { borderColor: rail, borderStyle: dashed ? "dashed" : "solid" }]} />
      <View style={{ flex: 1, paddingBottom: space(4) }}>{children}</View>
    </View>
  );
}

export function departureLabel(d: Departure): string {
  const parts = [
    `${modeName(d.mode)} ${d.line_number} w kierunku ${d.headsign}`,
    inMinutes(d.eta_min),
    `o ${d.departure_time}`,
    d.delay_min ? `opóźniony o ${d.delay_min} ${minutesPl(d.delay_min, "acc")}` : null,
    isLive(d.data_source) ? "na żywo" : "według rozkładu",
    d.vehicle.low_floor === "none" ? "wysokie stopnie" : lowFloorLabel(d.vehicle.low_floor),
  ];
  return parts.filter(Boolean).join(", ");
}

export function DepartureRow({ d }: { d: Departure }) {
  const delayed = d.delay_min > 0;
  return (
    <View style={styles.depRow} accessible accessibilityLabel={departureLabel(d)}>
      <LineBadge mode={d.mode} number={d.line_number} lowFloor={d.vehicle.low_floor} />
      <View style={{ flex: 1 }}>
        <T numberOfLines={1}>{d.headsign}</T>
        {delayed ? <T size={14} color={colors.delay}>opóźniony o {d.delay_min} min</T> : null}
      </View>
      <LiveIndicator dataSource={d.data_source} delayed={delayed} />
      <View style={{ alignItems: "flex-end" }}>
        <T variant="title" size={17}>{d.eta_min <= 0 ? "teraz" : `za ${d.eta_min} min`}</T>
        <View style={{ flexDirection: "row", gap: space(1) }}>
          {delayed ? <TimeChip time={minusMinutes(d.departure_time, d.delay_min)} kind="planned" /> : null}
          <T size={15} color={delayed ? colors.delay : isLive(d.data_source) ? colors.live : colors.textMuted}>
            {d.departure_time}
          </T>
        </View>
      </View>
    </View>
  );
}

export function TripView({ trip, target }: { trip: TripStatus; target?: string | null }) {
  const next = trip.remaining_stops[0];
  const idx = target ? trip.remaining_stops.findIndex((s) => s.name === target) : -1;
  const getOff = idx >= 0 ? (idx === 0 ? "Wysiadasz na następnym przystanku" : `Wysiadasz za ${stopsPl(idx + 1)}`) : null;
  return (
    <View style={{ gap: space(4) }}>
      <View accessible accessibilityLabel={`Linia ${trip.line_number}, pojazd ${trip.vehicle.side_number.split("").join(" ")}`}>
        <T variant="number" size={48}>{trip.line_number} · {trip.vehicle.side_number}</T>
      </View>
      {next ? (
        <Card accessible accessibilityLabel={`Następny przystanek ${next.name}, ${inMinutes(next.eta_min)}`}>
          <T variant="muted">Następny przystanek</T>
          <T variant="title" size={28}>{next.name}</T>
          <T variant="muted">{inMinutes(next.eta_min)}</T>
        </Card>
      ) : null}
      {getOff ? <T variant="title" size={26} color={colors.ticket}>{getOff}</T> : null}
      <Card style={{ gap: space(2) }}>
        <T variant="muted" accessibilityRole="header">Pozostałe przystanki</T>
        {trip.remaining_stops.map((s) => (
          <View key={s.stop_id} style={styles.between} accessible accessibilityLabel={`${s.name}, ${inMinutes(s.eta_min)}`}>
            <T variant={s.name === target ? "title" : "body"} color={s.name === target ? colors.ticket : undefined}>
              {s.name}
            </T>
            <T variant="muted">{s.eta_min} min</T>
          </View>
        ))}
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  routeCard: { flexDirection: "row", gap: space(4), alignItems: "center" },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: space(2) },
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space(2) },
  tlRow: { flexDirection: "row", gap: space(3) },
  tlTime: { width: 52, textAlign: "right" },
  rail: { width: 0, borderLeftWidth: 5, borderRadius: 3 },
  vehicle: { backgroundColor: colors.surfaceAlt, borderRadius: radius.chip, padding: space(3), gap: space(1) },
  depRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: space(3),
    paddingVertical: space(3),
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.surfaceAlt,
  },
});
