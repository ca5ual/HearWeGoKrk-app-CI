// 5.1 Voice home: a talk button that fills the screen. The conversation text (reply, transcript,
// last result, example phrases) lives in a panel behind the small "Tekst rozmowy" button.
import { router } from "expo-router";
import React, { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { DepartureRow, RouteCard } from "@/components/route";
import { TalkButton } from "@/components/TalkButton";
import { Button, Card, T } from "@/components/ui";
import { inMinutes } from "@/format";
import { MIN_TOUCH, colors, radius, space } from "@/theme";

const EXAMPLES = ["Jak dojadę na Rynek?", "Kiedy następna czternastka?", "Kup bilet"];

export default function VoiceHome() {
  const { connection, replyText, notice, replay, backendUrl } = useAgent();
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.page}>
      {connection !== "open" ? (
        <Card style={{ borderColor: colors.delay, borderWidth: 2 }}>
          <T variant="title" color={colors.delay}>
            {connection === "connecting" ? "Łączę z serwerem…" : "Brak połączenia z serwerem"}
          </T>
          <T variant="muted">{backendUrl} — zmień w ustawieniach (👤)</T>
        </Card>
      ) : null}
      {notice ? <T variant="title" color={colors.ticket}>{notice}</T> : null}

      <TalkButton />

      <View style={styles.bottom}>
        <SmallButton
          label="💬 Tekst rozmowy"
          a11y="Tekst rozmowy"
          hint="Pokazuje, co powiedział asystent"
          onPress={() => setOpen(true)}
        />
        {replyText ? <SmallButton label="🔁 Powtórz" a11y="Powtórz odpowiedź" onPress={replay} /> : null}
      </View>

      <ConversationPanel visible={open} onClose={() => setOpen(false)} />
    </View>
  );
}

function SmallButton({ label, a11y, hint, onPress }: { label: string; a11y: string; hint?: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      accessibilityHint={hint}
      style={({ pressed }) => [styles.small, { opacity: pressed ? 0.75 : 1 }]}
    >
      <T variant="title" size={16}>{label}</T>
    </Pressable>
  );
}

function ConversationPanel({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { replyText, transcript, sendText, replay } = useAgent();
  const empty = !replyText && !transcript;

  const go = (path: "/route/results" | "/departures" | "/trip") => {
    onClose();
    router.navigate(path);
  };
  const ask = (text: string) => {
    onClose();
    sendText(text);
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.panel} accessibilityViewIsModal>
        <View style={styles.panelHead}>
          <T variant="title" size={24} accessibilityRole="header">Tekst rozmowy</T>
          <Button kind="plain" label="Zamknij" onPress={onClose} />
        </View>
        <ScrollView contentContainerStyle={{ gap: space(5), paddingBottom: space(12) }}>
          {transcript ? (
            <View style={{ gap: space(1) }}>
              <T variant="muted">Ty</T>
              <T size={20}>„{transcript}”</T>
            </View>
          ) : null}
          {replyText ? (
            <View style={{ gap: space(1) }}>
              <T variant="muted">Asystent</T>
              <T variant="title" size={24} style={{ lineHeight: 32 }}>{replyText}</T>
              <Button kind="plain" label="🔁 Powtórz" onPress={replay} style={{ alignSelf: "flex-start" }} />
            </View>
          ) : null}

          <LastResult go={go} />

          {empty ? (
            <View style={{ gap: space(2) }}>
              <T variant="title">Jeszcze nic nie powiedziałeś.</T>
              <T variant="muted" accessibilityRole="header">Możesz powiedzieć na przykład:</T>
              {EXAMPLES.map((e) => (
                <Pressable
                  key={e}
                  onPress={() => ask(e)}
                  accessibilityRole="button"
                  accessibilityLabel={e}
                  accessibilityHint="Wysyła to polecenie do asystenta"
                  style={styles.example}
                >
                  <T>„{e}”</T>
                </Pressable>
              ))}
            </View>
          ) : null}
        </ScrollView>
      </View>
    </Modal>
  );
}

function LastResult({ go }: { go: (path: "/route/results" | "/departures" | "/trip") => void }) {
  const { lastUi } = useAgent();
  if (!lastUi) return null;
  if (lastUi.component === "route_results" && lastUi.data.status === "ok") {
    const r = lastUi.data;
    return <RouteCard it={r.best} dataSource={r.data_source} title={`Trasa do: ${r.destination}`} onPress={() => go("/route/results")} />;
  }
  if (lastUi.component === "departures") {
    const d = lastUi.data;
    return (
      <Pressable onPress={() => go("/departures")} accessibilityRole="button" accessibilityHint="Otwiera rozkład">
        <Card>
          <T variant="title">{d.stop_name}</T>
          {d.departures.slice(0, 2).map((x, i) => <DepartureRow key={i} d={x} />)}
        </Card>
      </Pressable>
    );
  }
  if (lastUi.component === "trip_live") {
    const t = lastUi.data;
    const next = t.remaining_stops[0];
    return (
      <Pressable onPress={() => go("/trip")} accessibilityRole="button" accessibilityHint="Otwiera widok podróży">
        <Card>
          <T variant="title" size={24}>{t.line_number} · {t.vehicle.side_number}</T>
          {next ? <T variant="muted">Następny: {next.name}, {inMinutes(next.eta_min)}</T> : null}
        </Card>
      </Pressable>
    );
  }
  return null;
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: space(4), gap: space(3) },
  bottom: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: space(2) },
  small: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
  panel: { flex: 1, backgroundColor: colors.bg, padding: space(4), paddingTop: space(10), gap: space(4) },
  panelHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(3) },
  example: {
    backgroundColor: colors.surface,
    borderRadius: radius.chip,
    padding: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
});
