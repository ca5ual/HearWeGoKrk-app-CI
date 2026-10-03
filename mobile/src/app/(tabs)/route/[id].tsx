// 5.4 Route detail: summary card, then the route as numbered steps (vehicle in the ride step).
import { useLocalSearchParams } from "expo-router";
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { TicketFab } from "@/components/money";
import { ItinerarySteps, RouteCard } from "@/components/route";
import { T } from "@/components/ui";
import { space } from "@/theme";

export default function RouteDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { ui } = useAgent();
  const r = ui.route_results;
  const it = r?.status === "ok" ? [r.best, ...r.alternatives][Number(id)] : undefined;

  if (!it || r?.status !== "ok") {
    return (
      <View style={styles.page}>
        <T variant="muted">Brak trasy.</T>
      </View>
    );
  }
  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={[styles.page, { gap: space(4), paddingBottom: space(24) }]}>
        <RouteCard it={it} dataSource={r.data_source} title={`Do: ${r.destination}`} />
        <ItinerarySteps it={it} destination={r.destination} />
      </ScrollView>
      <TicketFab />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4) },
});
