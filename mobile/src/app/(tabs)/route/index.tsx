// 5.2 Route search. The backend plans from the user's position only, so the origin is fixed
// ("Moja lokalizacja") and there is no time picker yet.
import { router } from "expo-router";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, TextInput, View } from "react-native";

import { useAnnounce } from "@/a11y";
import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { RouteCard } from "@/components/route";
import { Button, Card, IconText, T, inputOutline, switchColors } from "@/components/ui";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";

// Destinations the backend knows (mock/routes.json); one tap searches.
const QUICK = ["Rynek", "AGH", "Dworzec Główny", "Kampus UJ"];

export default function RouteSearch() {
  const { backendUrl, setRouteResult, sessionId, ui } = useAgent();
  const last = ui.route_results;
  const lastDest = last?.status === "ok" || last?.status === "no_route" ? last.destination : "";
  const [dest, setDest] = useState(lastDest);

  // A route asked by voice (or found here) -> keep its destination in the input.
  const [followed, setFollowed] = useState(last);
  if (last !== followed) {
    setFollowed(last);
    if (lastDest) setDest(lastDest);
  }
  const [lowFloor, setLowFloor] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useAnnounce(error);

  const search = async (to = dest) => {
    if (!to.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setRouteResult(await api.route(backendUrl, to.trim(), lowFloor, sessionId));
      router.push("/route/results");
    } catch {
      setError("Nie udało się połączyć z serwerem.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View style={{ gap: space(1) }}>
        <T variant="title" size={28} accessibilityRole="header">Dokąd jedziesz?</T>
        <IconText variant="muted" icon="map-pin">Z: Twoja lokalizacja · odjazd teraz</IconText>
      </View>

      <TextInput
        value={dest}
        onChangeText={setDest}
        onSubmitEditing={() => search()}
        placeholder="Wpisz cel podróży"
        placeholderTextColor={colors.textMuted}
        accessibilityLabel="Dokąd jedziesz"
        returnKeyType="search"
        style={styles.input}
      />
      <Button label={busy ? "Szukam…" : "Szukaj trasy"} onPress={() => search()} disabled={busy || !dest.trim()} />
      {error ? <T color={colors.delay}>{error}</T> : null}

      {last?.status === "ok" ? (
        <View style={{ gap: space(2) }}>
          <T variant="muted" accessibilityRole="header">Ostatnio wyszukana trasa</T>
          <RouteCard
            it={last.best}
            dataSource={last.data_source}
            title={`Do: ${last.destination}`}
            onPress={() => router.push("/route/results")}
          />
        </View>
      ) : null}

      <View style={{ gap: space(2) }}>
        <T variant="muted" accessibilityRole="header">Szybki wybór</T>
        <View style={styles.quick}>
          {QUICK.map((q) => (
            <Pressable
              key={q}
              onPress={() => {
                setDest(q);
                search(q);
              }}
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel={`Trasa do: ${q}`}
              style={({ pressed }) => [styles.quickItem, { opacity: pressed ? 0.75 : 1 }]}
            >
              <T variant="title" size={17}>{q}</T>
            </Pressable>
          ))}
        </View>
      </View>

      <Card style={styles.option}>
        <View style={{ flex: 1 }}>
          <IconText variant="title" size={17} icon="accessibility">Pojazdy niskopodłogowe</IconText>
          <T variant="muted" size={14}>Wybieraj tramwaje i autobusy bez stopni</T>
        </View>
        <Switch
          {...switchColors}
          value={lowFloor}
          onValueChange={setLowFloor}
          accessibilityLabel="Preferuj pojazdy niskopodłogowe"
        />
      </Card>

      <IconText variant="muted" size={14} icon="radio" iconColor={colors.live}>
        Odjazdy liczone z danych na żywo. Możesz też zapytać głosem w zakładce Mów.
      </IconText>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(5), paddingBottom: space(12) },
  input: {
    minHeight: MIN_TOUCH + 16,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.chip,
    paddingHorizontal: space(4),
    color: colors.text,
    fontFamily: font.title,
    fontSize: 20,
    ...inputOutline,
  },
  quick: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  quickItem: {
    backgroundColor: colors.surface,
    borderRadius: radius.chip,
    paddingHorizontal: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
  option: { flexDirection: "row", alignItems: "center", gap: space(3) },
});
