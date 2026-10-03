// 5.5 Departures board. Polls GET /stops/{id}/departures every 30 s while visible, unless the user
// paused it (WCAG 2.2.2: a list that changes under a screen reader must be stoppable).
// When the agent answers a departures question, the board jumps to that stop (and line).
import { useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { DepartureRow } from "@/components/route";
import { Button, Card, IconText, T, inputOutline } from "@/components/ui";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";
import type { Departure, Stop } from "@/types";

const DEMO_ORIGIN = "tauron_arena";

type ModeFilter = "all" | "tram" | "bus";
const MODE_FILTERS: readonly (readonly [ModeFilter, string])[] = [
  ["all", "Wszystkie"],
  ["tram", "Tramwaje"],
  ["bus", "Autobusy"],
];

export default function Departures() {
  const { backendUrl, ui } = useAgent();
  const [stops, setStops] = useState<Stop[]>([]);
  const [stopId, setStopId] = useState(ui.departures?.stop_id ?? DEMO_ORIGIN);
  const [deps, setDeps] = useState<Departure[] | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ModeFilter>("all");
  const [paused, setPaused] = useState(false);

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
      if (paused) return;
      const t = setInterval(load, 30000);
      return () => clearInterval(t);
    }, [load, paused]),
  );

  const q = query.trim().toLowerCase();
  const line = /^\d+$/.test(q) ? q : null;
  const stopMatches = useMemo(
    () => (q && !line ? stops.filter((s) => s.name.toLowerCase().includes(q)) : []),
    [q, line, stops],
  );
  const shown = (deps ?? []).filter(
    (d) => (mode === "all" || d.mode === mode) && (!line || d.line_number === line),
  );
  const stop = stops.find((s) => s.id === stopId);

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View accessible accessibilityRole="header" accessibilityLabel={`Przystanek ${stop?.name ?? stopId}`}>
        <T variant="muted">Przystanek</T>
        <T variant="title" size={28}>{stop?.name ?? stopId}</T>
      </View>

      <T variant="muted" size={14} importantForAccessibility="no">Zmień przystanek lub wpisz numer linii</T>
      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder="Zmień przystanek lub wpisz nr linii"
        placeholderTextColor={colors.textMuted}
        accessibilityLabel="Zmień przystanek albo wpisz numer linii"
        style={styles.input}
      />
      {stopMatches.length ? (
        <Card style={{ padding: space(2), gap: space(1) }}>
          {stopMatches.map((s) => (
            <Pressable
              key={s.id}
              onPress={() => {
                setStopId(s.id);
                setQuery("");
              }}
              accessibilityRole="button"
              accessibilityLabel={`Pokaż odjazdy z przystanku ${s.name}`}
              style={({ pressed }) => [styles.match, pressed && { backgroundColor: colors.surfaceAlt }]}
            >
              <IconText variant="title" size={17} icon="map-pin">{s.name}</IconText>
            </Pressable>
          ))}
        </Card>
      ) : null}

      <View style={styles.seg} accessibilityRole="tablist">
        {MODE_FILTERS.map(([m, label]) => (
          <Pressable
            key={m}
            onPress={() => setMode(m)}
            accessibilityRole="tab"
            accessibilityLabel={label}
            accessibilityState={{ selected: mode === m }}
            style={[styles.segItem, mode === m && { backgroundColor: colors.accent }]}
          >
            <T variant="title" size={15}>{label}</T>
          </Pressable>
        ))}
      </View>

      {line ? (
        <View style={styles.lineFilter}>
          <T variant="title" size={17} style={{ flex: 1 }}>Tylko linia {line}</T>
          <Button kind="plain" label="Pokaż wszystkie" onPress={() => setQuery("")} />
        </View>
      ) : null}

      <View style={styles.listHead}>
        <T variant="title" accessibilityRole="header">Najbliższe odjazdy</T>
        <Button
          kind="plain"
          icon={paused ? "play" : "pause"}
          label={paused ? "Wznów odświeżanie" : "Wstrzymaj odświeżanie"}
          accessibilityHint={paused ? "Lista znowu będzie się aktualizować co 30 sekund" : "Lista przestanie się zmieniać"}
          onPress={() => setPaused((p) => !p)}
        />
      </View>
      <T variant="muted" size={13}>
        {paused ? "Odświeżanie wstrzymane — lista się nie zmienia." : "Lista odświeża się co 30 s."}
      </T>
      <Card style={{ paddingVertical: space(1) }}>
        {deps === null ? <T variant="muted" style={styles.empty}>Brak danych.</T> : null}
        {deps && !shown.length ? <T variant="muted" style={styles.empty}>Brak odjazdów.</T> : null}
        {shown.map((d, i) => <DepartureRow key={`${d.line_id}-${d.departure_time}-${i}`} d={d} />)}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(4), paddingBottom: space(12) },
  input: {
    minHeight: MIN_TOUCH + 8,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.chip,
    paddingHorizontal: space(4),
    color: colors.text,
    fontFamily: font.body,
    fontSize: 17,
    ...inputOutline,
  },
  match: { borderRadius: radius.chip, padding: space(3), minHeight: MIN_TOUCH, justifyContent: "center" },
  seg: { flexDirection: "row", backgroundColor: colors.surface, borderRadius: radius.pill, padding: 4 },
  segItem: { flex: 1, minHeight: MIN_TOUCH, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  lineFilter: { flexDirection: "row", alignItems: "center", gap: space(3), flexWrap: "wrap" },
  listHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: space(2) },
  empty: { paddingVertical: space(3) },
});
