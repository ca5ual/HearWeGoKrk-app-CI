// 5.3 Route results: one RouteCard per itinerary (best first).
import { router } from "expo-router";
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { TicketFab } from "@/components/money";
import { RouteCard } from "@/components/route";
import { Button, Card, T } from "@/components/ui";
import { colors, space } from "@/theme";

export default function RouteResults() {
  const { ui, backendUrl, setRouteResult } = useAgent();
  const r = ui.route_results;

  const pick = async (option: string) => {
    try {
      setRouteResult(await api.route(backendUrl, option.toLowerCase()));
    } catch {}
  };

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={styles.page}>
        {!r ? <T variant="muted">Zapytaj o trasę głosem albo w zakładce Trasa.</T> : null}

        {r?.status === "ambiguous" ? (
          <Card style={{ gap: space(3) }}>
            <T variant="title">Które miejsce?</T>
            {r.options.map((o) => <Button key={o} kind="plain" label={o} onPress={() => pick(o)} />)}
          </Card>
        ) : null}
        {r?.status === "not_found" ? <T variant="title">Nie znam tego miejsca. Spróbuj: Rynek, AGH, Dworzec Główny.</T> : null}
        {r?.status === "no_route" ? <T variant="title">Brak połączenia do: {r.destination}.</T> : null}

        {r?.status === "ok" ? (
          <>
            <View style={styles.header} accessible accessibilityLabel={`Z mojej lokalizacji do: ${r.destination}`}>
              <View style={styles.dots}>
                <View style={[styles.dot, { backgroundColor: colors.depart }]} />
                <View style={styles.line} />
                <View style={[styles.dot, { backgroundColor: colors.arrive }]} />
              </View>
              <View style={{ gap: space(4) }}>
                <T variant="muted">Moja lokalizacja</T>
                <T variant="title">{r.destination}</T>
              </View>
            </View>
            {[r.best, ...r.alternatives].map((it, i) => (
              <RouteCard key={i} it={it} dataSource={r.data_source} onPress={() => router.push(`/route/${i}`)} />
            ))}
          </>
        ) : null}
      </ScrollView>
      <TicketFab />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(3), paddingBottom: space(24) },
  header: { flexDirection: "row", gap: space(3), paddingVertical: space(2) },
  dots: { alignItems: "center", paddingVertical: space(1) },
  dot: { width: 12, height: 12, borderRadius: 6 },
  line: { flex: 1, width: 2, backgroundColor: colors.textMuted, marginVertical: 2 },
});
