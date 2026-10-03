// 5.4 Route detail: sticky summary + vertical timeline with the vehicle row.
import { useLocalSearchParams } from "expo-router";
import React from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { TicketFab } from "@/components/money";
import { ItineraryTimeline, RouteCard } from "@/components/route";
import { T } from "@/components/ui";
import { colors, space } from "@/theme";

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
      <View style={styles.sticky}>
        <RouteCard it={it} dataSource={r.data_source} />
      </View>
      <ScrollView contentContainerStyle={[styles.page, { paddingBottom: space(24) }]}>
        <ItineraryTimeline it={it} />
      </ScrollView>
      <TicketFab />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4) },
  sticky: { padding: space(4), paddingBottom: space(2), backgroundColor: colors.bg },
});
