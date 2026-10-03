// 5.2 Route search. The backend plans from the user's position only, so the origin is fixed
// ("Moja lokalizacja") and there is no time picker yet.
import { router } from "expo-router";
import React, { useState } from "react";
import { ScrollView, StyleSheet, Switch, TextInput, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { Button, Card, T } from "@/components/ui";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";

export default function RouteSearch() {
  const { backendUrl, setRouteResult } = useAgent();
  const [dest, setDest] = useState("");
  const [lowFloor, setLowFloor] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!dest.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setRouteResult(await api.route(backendUrl, dest.trim(), lowFloor));
      router.push("/route/results");
    } catch {
      setError("Nie udało się połączyć z serwerem.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Card style={{ gap: space(3) }}>
        <View style={styles.field} accessible accessibilityLabel="Skąd: moja lokalizacja">
          <T variant="muted" size={13}>Skąd</T>
          <T variant="title" size={18}>📍 Moja lokalizacja</T>
        </View>
        <View style={styles.field}>
          <T variant="muted" size={13}>Dokąd</T>
          <TextInput
            value={dest}
            onChangeText={setDest}
            onSubmitEditing={search}
            placeholder="np. Rynek, AGH, Dworzec Główny"
            placeholderTextColor={colors.textMuted}
            accessibilityLabel="Dokąd"
            returnKeyType="search"
            style={styles.input}
          />
        </View>
      </Card>

      <View style={styles.pills}>
        <View style={styles.pill} accessible accessibilityLabel="Odjazd: teraz">
          <T variant="title" size={15}>Teraz</T>
        </View>
        <View style={[styles.pill, { flexDirection: "row", gap: space(2), alignItems: "center" }]}>
          <T variant="title" size={15}>♿ Niskopodłogowe</T>
          <Switch
            value={lowFloor}
            onValueChange={setLowFloor}
            accessibilityLabel="Preferuj pojazdy niskopodłogowe"
            trackColor={{ true: colors.accent, false: colors.surfaceAlt }}
          />
        </View>
      </View>

      <View style={[styles.pill, { alignSelf: "flex-start" }]} accessible accessibilityLabel="Dane na żywo dostępne">
        <T size={14} color={colors.live}>((•)) dane na żywo</T>
      </View>

      {error ? <T color={colors.delay}>{error}</T> : null}
      <Button label={busy ? "Szukam…" : "Pokaż trasy →"} onPress={search} disabled={busy || !dest.trim()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(4) },
  field: { gap: space(1), backgroundColor: colors.surfaceAlt, borderRadius: radius.chip, padding: space(3) },
  input: { color: colors.text, fontFamily: font.title, fontSize: 18, minHeight: MIN_TOUCH, padding: 0 },
  pills: { flexDirection: "row", gap: space(2), flexWrap: "wrap" },
  pill: {
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
});
