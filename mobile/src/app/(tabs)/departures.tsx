// 5.5 Departures board. Polls GET /stops/{id}/departures every 30 s while visible.
// When the agent answers a departures question, the board jumps to that stop (and line).
import { useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { DepartureRow } from "@/components/route";
import { Card, T } from "@/components/ui";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";
import type { Departure, Mode, Stop } from "@/types";

const DEMO_ORIGIN = "tauron_arena";

export default function Departures() {
  const { backendUrl, ui } = useAgent();
  const [stops, setStops] = useState<Stop[]>([]);
  const [stopId, setStopId] = useState(ui.departures?.stop_id ?? DEMO_ORIGIN);
  const [deps, setDeps] = useState<Departure[] | null>(null);
  const [query, setQuery] = useState("");
  const [modes, setModes] = useState<Record<Mode, boolean>>({ tram: true, bus: true, train: true });

  useEffect(() => {
    api.stops(backendUrl).then(setStops).catch(() => {});
  }, [backendUrl]);

  // Agent result -> follow it.
  const [followed, setFollowed] = useState(ui.departures);
  if (ui.departures !== followed) {
    const d = ui.departures;
    setFollowed(d);
    if (d) {
      setStopId(d.stop_id);
      setDeps(d.departures);
      const lines = new Set(d.departures.map((x) => x.line_number));
      setQuery(lines.size === 1 ? [...lines][0] : "");
    }
  }

  const load = useCallback(() => {
    api.departures(backendUrl, stopId, 10).then(setDeps).catch(() => setDeps(null));
  }, [backendUrl, stopId]);

  useFocusEffect(
    useCallback(() => {
      load();
      const t = setInterval(load, 30000);
      return () => clearInterval(t);
    }, [load]),
  );

  const q = query.trim().toLowerCase();
  const stopMatches = useMemo(
    () => (q && !/^\d+$/.test(q) ? stops.filter((s) => s.name.toLowerCase().includes(q)) : []),
    [q, stops],
  );
  const shown = (deps ?? []).filter(
    (d) => modes[d.mode] && (!/^\d+$/.test(q) || d.line_number === q),
  );
  const stop = stops.find((s) => s.id === stopId);

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder="Wyszukaj linię lub przystanek…"
        placeholderTextColor={colors.textMuted}
        accessibilityLabel="Wyszukaj linię lub przystanek"
        style={styles.input}
      />
      {stopMatches.map((s) => (
        <Pressable
          key={s.id}
          onPress={() => {
            setStopId(s.id);
            setQuery("");
          }}
          accessibilityRole="button"
          accessibilityLabel={`Przystanek ${s.name}`}
          style={styles.match}
        >
          <T>{s.name}</T>
        </Pressable>
      ))}

      <View style={styles.chips}>
        {(
          [
            ["tram", "Tramwaje"],
            ["bus", "Autobusy"],
          ] as const
        ).map(([m, label]) => (
          <Pressable
            key={m}
            onPress={() => setModes((x) => ({ ...x, [m]: !x[m] }))}
            accessibilityRole="checkbox"
            accessibilityLabel={label}
            accessibilityState={{ checked: modes[m] }}
            style={[styles.chip, modes[m] && { backgroundColor: colors.accent }]}
          >
            <T variant="title" size={15}>{label}</T>
          </Pressable>
        ))}
      </View>

      <T variant="title" accessibilityRole="header">Odjazdy</T>
      <Card>
        <T variant="title" size={18}>{stop?.name ?? stopId} ›</T>
        {deps === null ? <T variant="muted">Brak danych.</T> : null}
        {deps && !shown.length ? <T variant="muted">Brak odjazdów.</T> : null}
        {shown.map((d, i) => <DepartureRow key={`${d.line_id}-${d.departure_time}-${i}`} d={d} />)}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(3), paddingBottom: space(12) },
  input: {
    minHeight: MIN_TOUCH + 8,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: space(5),
    color: colors.text,
    fontFamily: font.body,
    fontSize: 17,
  },
  match: { backgroundColor: colors.surface, borderRadius: radius.chip, padding: space(3), minHeight: MIN_TOUCH, justifyContent: "center" },
  chips: { flexDirection: "row", gap: space(2) },
  chip: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
});
