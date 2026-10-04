// 5.3 Route results: one RouteCard per itinerary (best first).
import { router } from "expo-router";
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { TicketFab } from "@/components/money";
import { RouteCard } from "@/components/route";
import { Button, Card, T } from "@/components/ui";
import { space } from "@/theme";

export default function RouteResults() {
  const { ui, backendUrl, setRouteResult, sessionId } = useAgent();
  const r = ui.route_results;

  const pick = async (option: string) => {
    try {
      setRouteResult(await api.route(backendUrl, option.toLowerCase(), undefined, sessionId));
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
            <View accessible accessibilityRole="header" accessibilityLabel={`Trasy do: ${r.destination}`}>
              <T variant="muted">Trasy do</T>
              <T variant="title" size={26}>{r.destination}</T>
            </View>
            {[r.best, ...r.alternatives].map((it, i) => (
              <RouteCard
                key={i}
                it={it}
                dataSource={r.data_source}
                title={i === 0 ? "Polecana trasa" : `Inna trasa ${i}`}
                onPress={() => router.push(`/route/${i}`)}
              />
            ))}
          </>
        ) : null}

        <Button kind="plain" label="Zmień cel podróży" onPress={() => router.navigate("/route")} />
      </ScrollView>
      <TicketFab />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(3), paddingBottom: space(24) },
});
