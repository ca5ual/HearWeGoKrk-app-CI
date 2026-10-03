// FRONTEND.md section 4: LineBadge, TimeChip, WalkSegment, LiveIndicator, CountdownBig.
import React from "react";
import { StyleSheet, View } from "react-native";

import { lowFloorLabel, minutesPl, modeName } from "../format";
import { colors, radius, space } from "../theme";
import type { LowFloor, Mode } from "../types";
import { T } from "./ui";

const MODE_ICON: Record<Mode, string> = { tram: "🚋", bus: "🚌", train: "🚆" };

export function LineBadge({ mode, number, lowFloor }: { mode: Mode; number: string; lowFloor?: LowFloor }) {
  const label = [modeName(mode), number, lowFloorLabel(lowFloor)].filter(Boolean).join(" ");
  return (
    <View style={styles.badgeRow} accessible accessibilityLabel={label}>
      <T size={18} importantForAccessibility="no">{MODE_ICON[mode]}</T>
      <View style={styles.badge}>
        <T variant="title" size={18}>{number}</T>
      </View>
      {lowFloor === "full" || lowFloor === "partial" ? <T size={16}>♿</T> : null}
      {lowFloor === "none" ? <T size={13} color={colors.delay}>⚠ stopnie</T> : null}
    </View>
  );
}

export function TimeChip({ time, kind }: { time: string; kind: "depart" | "arrive" | "planned" }) {
  if (kind === "planned") {
    return (
      <T variant="muted" style={{ textDecorationLine: "line-through" }} accessibilityLabel={`planowo ${time}`}>
        {time}
      </T>
    );
  }
  return (
    <View
      style={[styles.chip, { backgroundColor: kind === "depart" ? colors.depart : colors.arrive }]}
      accessible
      accessibilityLabel={`${kind === "depart" ? "odjazd" : "przyjazd"} ${time}`}
    >
      <T variant="title" size={16}>{time}</T>
    </View>
  );
}

export function WalkSegment({ minutes }: { minutes: number }) {
  return (
    <View style={styles.badgeRow} accessible accessibilityLabel={`dojście ${minutes} ${minutesPl(minutes)}`}>
      <T size={16}>🚶</T>
      <T variant="muted">{minutes} min</T>
    </View>
  );
}

export function LiveIndicator({ dataSource, delayed }: { dataSource?: string; delayed?: boolean }) {
  const live = dataSource === "live" || dataSource === "simulated_live";
  if (!live) return <T variant="muted" size={13} accessibilityLabel="według rozkładu">rozkład</T>;
  return (
    <T
      size={14}
      color={delayed ? colors.delay : colors.live}
      accessibilityLabel={delayed ? "dane na żywo, opóźniony" : "dane na żywo"}
    >
      ((•))
    </T>
  );
}

export function CountdownBig({ minutes }: { minutes: number }) {
  const n = Math.max(0, minutes);
  return (
    <View accessible accessibilityLabel={`Odjazd za ${n} ${minutesPl(n, "acc")}`} style={{ alignItems: "center" }}>
      <T variant="muted" size={13}>Odjazd za:</T>
      <T variant="number" size={44} style={{ lineHeight: 50 }}>{n < 10 ? `0${n}` : n}</T>
      <T variant="muted" size={13}>min</T>
    </View>
  );
}

const styles = StyleSheet.create({
  badgeRow: { flexDirection: "row", alignItems: "center", gap: space(1) },
  badge: {
    borderWidth: 2,
    borderColor: colors.text,
    borderRadius: radius.chip,
    paddingHorizontal: space(2),
    paddingVertical: 2,
    minWidth: 40,
    alignItems: "center",
  },
  chip: { borderRadius: radius.pill, paddingHorizontal: space(3), paddingVertical: space(1) },
});
