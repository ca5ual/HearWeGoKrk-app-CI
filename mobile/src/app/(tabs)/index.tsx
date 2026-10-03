// 5.1 Voice home: talk button, agent reply, transcript, "Powtórz", last result card.
import { router } from "expo-router";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { DepartureRow, RouteCard } from "@/components/route";
import { TalkButton } from "@/components/TalkButton";
import { Button, Card, T } from "@/components/ui";
import { inMinutes } from "@/format";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";

const EXAMPLES = ["Jak dojadę na Rynek?", "Kiedy następna czternastka?", "Kup bilet"];

export default function VoiceHome() {
  const { connection, replyText, transcript, notice, lastUi, sendText, replay, backendUrl } = useAgent();
  const [typed, setTyped] = useState("");
  const empty = !replyText && !transcript;

  const submit = () => {
    sendText(typed);
    setTyped("");
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      {connection !== "open" ? (
        <Card style={{ borderColor: colors.delay, borderWidth: 2 }}>
          <T variant="title" color={colors.delay}>
            {connection === "connecting" ? "Łączę z serwerem…" : "Brak połączenia z serwerem"}
          </T>
          <T variant="muted">{backendUrl} — zmień w ustawieniach (👤)</T>
        </Card>
      ) : null}

      <View style={{ minHeight: 96, justifyContent: "flex-end" }}>
        {replyText ? (
          <T variant="title" size={26} style={{ lineHeight: 34 }}>{replyText}</T>
        ) : (
          <T variant="title" size={26}>Cześć! W czym pomóc?</T>
        )}
        {notice ? <T variant="title" color={colors.ticket}>{notice}</T> : null}
      </View>

      <View style={{ alignItems: "center" }}>
        <TalkButton />
      </View>

      {transcript ? <T variant="muted" accessibilityLabel={`Powiedziałeś: ${transcript}`}>„{transcript}”</T> : null}

      {replyText ? <Button kind="plain" label="Powtórz" onPress={replay} /> : null}

      {empty ? (
        <View style={{ gap: space(2) }}>
          <T variant="muted" accessibilityRole="header">Możesz powiedzieć na przykład:</T>
          {EXAMPLES.map((e) => (
            <Pressable
              key={e}
              onPress={() => sendText(e)}
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

      <LastResult />

      {/* Typed input: for testing without audio, and an accessible alternative to speech. */}
      <View style={styles.inputRow}>
        <TextInput
          value={typed}
          onChangeText={setTyped}
          onSubmitEditing={submit}
          placeholder="Albo napisz…"
          placeholderTextColor={colors.textMuted}
          accessibilityLabel="Napisz polecenie"
          returnKeyType="send"
          style={styles.input}
        />
        <Button label="Wyślij" onPress={submit} disabled={!typed.trim()} />
      </View>
    </ScrollView>
  );

  function LastResult() {
    if (!lastUi) return null;
    if (lastUi.component === "route_results" && lastUi.data.status === "ok") {
      const r = lastUi.data;
      return <RouteCard it={r.best} dataSource={r.data_source} onPress={() => router.navigate("/route/results")} />;
    }
    if (lastUi.component === "departures") {
      const d = lastUi.data;
      return (
        <Pressable onPress={() => router.navigate("/departures")} accessibilityRole="button" accessibilityHint="Otwiera rozkład">
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
        <Pressable onPress={() => router.navigate("/trip")} accessibilityRole="button" accessibilityHint="Otwiera widok podróży">
          <Card>
            <T variant="title" size={24}>{t.line_number} · {t.vehicle.side_number}</T>
            {next ? <T variant="muted">Następny: {next.name}, {inMinutes(next.eta_min)}</T> : null}
          </Card>
        </Pressable>
      );
    }
    return null;
  }
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(5), paddingBottom: space(12) },
  example: {
    backgroundColor: colors.surface,
    borderRadius: radius.chip,
    padding: space(4),
    minHeight: MIN_TOUCH,
    justifyContent: "center",
  },
  inputRow: { flexDirection: "row", gap: space(2), alignItems: "center" },
  input: {
    flex: 1,
    minHeight: MIN_TOUCH + 8,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: space(5),
    color: colors.text,
    fontFamily: font.body,
    fontSize: 17,
  },
});
