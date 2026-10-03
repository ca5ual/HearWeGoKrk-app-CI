// 5.6 Tickets: shop (catalog) + "Twoje bilety". Buying goes through the agent and the 5.7 modal.
import { useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { AccessibilityInfo, FlatList, Pressable, ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { TicketFab } from "@/components/money";
import { Card, T } from "@/components/ui";
import { pricePl } from "@/format";
import { MIN_TOUCH, colors, radius, space } from "@/theme";
import type { Ticket } from "@/types";

export default function Tickets() {
  const { backendUrl, ui, wallet, refreshWallet, headphones } = useAgent();
  const [tab, setTab] = useState<"shop" | "mine">("shop");
  const [fare, setFare] = useState<"u" | "n">("n");
  const [catalog, setCatalog] = useState<Ticket[]>([]);
  const [screenReader, setScreenReader] = useState(false);

  useEffect(() => {
    AccessibilityInfo.isScreenReaderEnabled().then(setScreenReader);
    const sub = AccessibilityInfo.addEventListener("screenReaderChanged", setScreenReader);
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (ui.ticket_shop) setCatalog(ui.ticket_shop.tickets);
    else api.catalog(backendUrl).then(setCatalog).catch(() => {});
  }, [backendUrl, ui.ticket_shop]);

  useFocusEffect(useCallback(() => refreshWallet(), [refreshWallet]));

  const items = catalog.filter((t) => t.id.endsWith(`_${fare}`));
  const active = wallet?.active_tickets ?? []; // already filtered to valid ones by the backend

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={styles.page}>
        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            ["shop", "Sklep"],
            ["mine", "Twoje bilety"],
          ]}
        />

        {tab === "shop" ? (
          <>
            <Segmented
              value={fare}
              onChange={setFare}
              options={[
                ["u", "Ulgowe"],
                ["n", "Normalne"],
              ]}
            />
            <T variant="title" accessibilityRole="header">Czasowe</T>
            {screenReader ? (
              items.map((t) => <TicketCard key={t.id} t={t} />)
            ) : (
              <FlatList
                horizontal
                data={items}
                keyExtractor={(t) => t.id}
                renderItem={({ item }) => <TicketCard t={item} />}
                ItemSeparatorComponent={() => <View style={{ width: space(3) }} />}
                showsHorizontalScrollIndicator={false}
              />
            )}
            <T variant="muted">Powiedz „kup bilet” albo stuknij 🛒 — zawsze poproszę o potwierdzenie.</T>
          </>
        ) : (
          <>
            {!active.length ? <T variant="muted">Nie masz aktywnych biletów.</T> : null}
            {active.map((t, i) => (
              <Card
                key={i}
                accessible
                accessibilityLabel={`${t.name_pl}, ważny do ${t.valid_until.slice(11, 16)}, pojazd ${t.vehicle ?? "brak"}`}
                style={{ gap: space(1), borderLeftWidth: 6, borderLeftColor: colors.ticket }}
              >
                <T variant="title">{t.name_pl}</T>
                <T variant="number" size={32}>do {t.valid_until.slice(11, 16)}</T>
                <T variant="muted">Skasowany w pojeździe {t.vehicle ?? "—"}</T>
                {headphones ? <T variant="muted">{pricePl(t.price_pln)}</T> : null}
              </Card>
            ))}
          </>
        )}
      </ScrollView>
      <TicketFab />
    </View>
  );
}

function TicketCard({ t }: { t: Ticket }) {
  const reduced = t.id.endsWith("_u");
  const label = `${t.name_pl}, strefa ${t.zones}, ${pricePl(t.price_pln)}`;
  return (
    <Card style={styles.ticket} accessible accessibilityLabel={label}>
      <View style={[styles.strip, { backgroundColor: reduced ? colors.arrive : colors.depart }]}>
        <T variant="title" size={14}>{reduced ? "ULGOWY" : "NORMALNY"}</T>
      </View>
      <View style={{ padding: space(4), gap: space(1) }}>
        <T variant="muted" size={13}>ZTP w Krakowie</T>
        <T variant="muted" size={13}>Strefa: {t.zones}</T>
        <T variant="number" size={56} style={{ lineHeight: 62 }}>{t.valid_min}</T>
        <T>{t.valid_min === 30 ? "minut lub 1 przejazd" : "minut"}</T>
        <T variant="title" size={22} color={colors.ticket}>{pricePl(t.price_pln)}</T>
      </View>
    </Card>
  );
}

function Segmented<V extends string>({
  value,
  onChange,
  options,
}: {
  value: V;
  onChange: (v: V) => void;
  options: readonly (readonly [V, string])[];
}) {
  return (
    <View style={styles.seg} accessibilityRole="tablist">
      {options.map(([v, label]) => (
        <Pressable
          key={v}
          onPress={() => onChange(v)}
          accessibilityRole="tab"
          accessibilityLabel={label}
          accessibilityState={{ selected: v === value }}
          style={[styles.segItem, v === value && { backgroundColor: colors.accent }]}
        >
          <T variant="title" size={16}>{label}</T>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(4), paddingBottom: space(24) },
  seg: { flexDirection: "row", backgroundColor: colors.surfaceAlt, borderRadius: radius.pill, padding: 4 },
  segItem: { flex: 1, minHeight: MIN_TOUCH, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  ticket: { padding: 0, overflow: "hidden", minWidth: 200 },
  strip: { paddingHorizontal: space(4), paddingVertical: space(2) },
});
