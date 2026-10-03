// RouteCard (5.3), ItinerarySteps (5.4), DepartureRow (5.5), TripView (5.8).
import React from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { inMinutes, isLive, lowFloorLabel, minusMinutes, minutesPl, modeName, stopsPl } from "../format";
import { colors, radius, space } from "../theme";
import type { Departure, Itinerary, RideLeg, TripStatus } from "../types";
import { LineBox, LiveIndicator, LowFloorNote, MODE_ICON, modeTitle } from "./transit";
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

/** One itinerary: when to leave, how long it takes, and the legs in plain words. */
export function RouteCard({
  it,
  dataSource,
  title,
  onPress,
}: {
  it: Itinerary;
  dataSource?: string;
  title?: string;
  onPress?: () => void;
}) {
  const dep = minutesToDeparture(it);
  const first = rides(it)[0];
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessible
      accessibilityRole={onPress ? "button" : undefined}
      accessibilityLabel={[title, itineraryLabel(it)].filter(Boolean).join(". ")}
      accessibilityHint={onPress ? "Otwiera szczegóły trasy" : undefined}
      style={({ pressed }) => ({ opacity: pressed ? 0.8 : 1 })}
    >
      <Card style={{ gap: space(3) }}>
        {title ? <T variant="title" size={15} color={colors.textMuted}>{title}</T> : null}
        <View style={styles.between}>
          <View>
            <T variant="number" size={34} style={{ lineHeight: 40 }}>{dep <= 0 ? "teraz" : `za ${dep} min`}</T>
            <T variant="muted">odjazd {first?.departure ?? "—"}</T>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <T variant="title" size={22}>{it.total_min} min</T>
            <T variant="muted">przyjazd {it.arrival}</T>
          </View>
        </View>
        <View style={styles.legs}>
          {it.legs.map((leg, i) =>
            leg.type === "walk" ? (
              <T key={i} variant="muted">🚶 Pieszo {leg.minutes} min</T>
            ) : (
              <View key={i} style={{ gap: 2 }}>
                <T variant="title" size={17}>
                  {MODE_ICON[leg.mode]} {modeTitle(leg.mode)} {leg.line_number} → {leg.headsign}
                </T>
                <LowFloorNote lowFloor={leg.vehicle.low_floor} />
              </View>
            ),
          )}
        </View>
        <View style={styles.between}>
          <LiveIndicator dataSource={dataSource} />
          {onPress ? <T variant="title" size={16}>Szczegóły ›</T> : null}
        </View>
      </Card>
    </Pressable>
  );
}

/** Route detail as numbered steps: one card per thing the user has to do. */
export function ItinerarySteps({ it, destination }: { it: Itinerary; destination: string }) {
  return (
    <View style={{ gap: space(3) }}>
      {it.legs.map((leg, i) => {
        const step = `Krok ${i + 1}`;
        if (leg.type === "walk") {
          return (
            <Card
              key={i}
              style={styles.step}
              accessible
              accessibilityLabel={`${step}. Idź ${leg.meters} metrów, ${leg.minutes} ${minutesPl(leg.minutes)}. ${leg.instruction_pl}. Na miejscu o ${leg.arrive}.`}
            >
              <T variant="muted">{step}</T>
              <T variant="title" size={22}>🚶 Idź {leg.meters} m</T>
              <T>{leg.instruction_pl}</T>
              <Fact label="Czas" value={`${leg.minutes} min`} />
              <Fact label="Na miejscu" value={leg.arrive} />
            </Card>
          );
        }
        const v = leg.vehicle;
        const off = plus(leg.departure, leg.ride_min);
        return (
          <Card key={i} style={styles.step}>
            <View
              accessible
              accessibilityLabel={`${step}. Wsiądź na przystanku ${leg.from} do: ${modeName(leg.mode)} ${leg.line_number} w kierunku ${leg.headsign}. Odjazd ${leg.departure}.`}
              style={{ gap: space(2) }}
            >
              <T variant="muted">{step}</T>
              <View style={styles.rideHead}>
                <LineBox mode={leg.mode} number={leg.line_number} />
                <View style={{ flex: 1 }}>
                  <T variant="title" size={20}>Wsiądź: {modeName(leg.mode)} {leg.line_number}</T>
                  <T variant="muted">w kierunku {leg.headsign}</T>
                </View>
              </View>
              <Fact label="Przystanek" value={leg.from} />
              <Fact label="Odjazd" value={leg.departure} />
            </View>
            <View
              style={styles.vehicle}
              accessible
              accessibilityLabel={`Pojazd ${v.side_number.split("").join(" ")}, ${v.model}, ${lowFloorLabel(v.low_floor)}. ${v.boarding_hint_pl}`}
            >
              <T variant="muted" size={13}>Pojazd</T>
              <T variant="number" size={30}>{v.side_number}</T>
              <T variant="muted">{v.model}</T>
              <LowFloorNote lowFloor={v.low_floor} size={16} />
              <T>{v.boarding_hint_pl}</T>
            </View>
            <View
              accessible
              accessibilityLabel={`Wysiądź na przystanku ${leg.to} o ${off}, po ${leg.ride_min} ${minutesPl(leg.ride_min, "acc")} jazdy.`}
              style={{ gap: space(2) }}
            >
              <Fact label="Wysiądź" value={leg.to} />
              <Fact label="O godzinie" value={`${off} (${leg.ride_min} min jazdy)`} />
            </View>
          </Card>
        );
      })}
      <Card style={[styles.step, styles.goal]} accessible accessibilityLabel={`Cel: ${destination}, przyjazd ${it.arrival}`}>
        <T variant="muted">Cel</T>
        <T variant="title" size={22}>📍 {destination}</T>
        <Fact label="Przyjazd" value={it.arrival} />
      </Card>
    </View>
  );
}

/** "Label ........ value" row; wraps under large font scaling. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <T variant="muted">{label}</T>
      <T variant="title" size={17} style={{ flexShrink: 1, textAlign: "right" }}>{value}</T>
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
  const live = isLive(d.data_source);
  return (
    <View style={styles.depRow} accessible accessibilityLabel={departureLabel(d)}>
      <LineBox mode={d.mode} number={d.line_number} />
      <View style={{ flex: 1, gap: 2 }}>
        <T variant="title" size={17} numberOfLines={2}>→ {d.headsign}</T>
        <LowFloorNote lowFloor={d.vehicle.low_floor} />
        {delayed ? (
          <T size={14} color={colors.delay}>
            Opóźniony o {d.delay_min} min (planowo {minusMinutes(d.departure_time, d.delay_min)})
          </T>
        ) : null}
      </View>
      <View style={{ alignItems: "flex-end", gap: 2 }}>
        <T variant="number" size={24} style={{ lineHeight: 28 }}>{d.eta_min <= 0 ? "teraz" : `${d.eta_min} min`}</T>
        <T size={15} color={delayed ? colors.delay : live ? colors.live : colors.textMuted}>{d.departure_time}</T>
        <LiveIndicator dataSource={d.data_source} delayed={delayed} />
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
  between: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space(2), flexWrap: "wrap" },
  legs: { gap: space(2), borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.surfaceAlt, paddingTop: space(3) },
  step: { gap: space(2) },
  goal: { borderWidth: 2, borderColor: colors.arrive },
  rideHead: { flexDirection: "row", alignItems: "center", gap: space(3) },
  fact: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: space(3), flexWrap: "wrap" },
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
