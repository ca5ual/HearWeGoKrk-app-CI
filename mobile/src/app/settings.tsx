// Profile / settings + hidden demo controls (README 4.3: /demo/reset, /demo/gps).
import React, { useState } from "react";
import { ScrollView, StyleSheet, Switch, TextInput, View } from "react-native";

import { useAgent } from "@/agent/AgentContext";
import { api } from "@/api";
import { Button, Card, IconText, T, inputOutline, switchColors } from "@/components/ui";
import { MIN_TOUCH, colors, font, radius, space } from "@/theme";

export default function Settings() {
  const { backendUrl, setBackendUrl, connection, headphones, setHeadphones, lang, setLang, refreshWallet } = useAgent();
  const [url, setUrl] = useState(backendUrl);
  const [demo, setDemo] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  const run = (label: string, fn: () => Promise<unknown>) => async () => {
    try {
      await fn();
      setStatus({ ok: true, text: label });
      refreshWallet();
    } catch (e) {
      setStatus({ ok: false, text: `${label}: ${String(e)}` });
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Card style={styles.card}>
        <Row label="Mam słuchawki" hint="Bez słuchawek kwoty nie są czytane na głos">
          <Switch {...switchColors} value={headphones} onValueChange={setHeadphones} accessibilityLabel="Mam słuchawki" />
        </Row>
        <Row label="English">
          <Switch {...switchColors} value={lang === "en"} onValueChange={(v) => setLang(v ? "en" : "pl")} accessibilityLabel="Odpowiedzi po angielsku" />
        </Row>
      </Card>

      <Card style={styles.card}>
        <T variant="title">Serwer</T>
        <T variant="muted">
          Status: {connection === "open" ? "połączono" : connection === "connecting" ? "łączę…" : "brak połączenia"}
        </T>
        <T variant="muted" size={14}>Adres serwera</T>
        <TextInput
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          accessibilityLabel="Adres serwera"
          style={styles.input}
        />
        <Button kind="plain" label="Połącz" onPress={() => setBackendUrl(url.trim().replace(/\/$/, ""))} />
      </Card>

      <Card style={styles.card}>
        <Row label="Tryb demo (scena)">
          <Switch {...switchColors} value={demo} onValueChange={setDemo} accessibilityLabel="Tryb demo" />
        </Row>
        {demo ? (
          <View style={{ gap: space(2) }}>
            <Button kind="plain" label="Reset demo (start)" onPress={run("reset", () => api.demoReset(backendUrl, 0))} />
            <Button
              kind="plain"
              label="Wsiadam do RZ612 (+12 min)"
              onPress={run("RZ612", async () => {
                await api.demoReset(backendUrl, 12);
                await api.demoGps(backendUrl, "RZ612");
              })}
            />
            <Button kind="plain" label="Wyczyść sztuczny GPS" onPress={run("GPS", () => api.demoGpsClear(backendUrl))} />
            {status ? (
              <IconText
                accessibilityLiveRegion="polite" variant="muted" icon={status.ok ? "check" : "x"} iconColor={status.ok ? colors.live : colors.delay}>
                {status.text}
              </IconText>
            ) : null}
          </View>
        ) : null}
      </Card>
    </ScrollView>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <T variant="title" size={17}>{label}</T>
        {hint ? <T variant="muted" size={14}>{hint}</T> : null}
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space(4), gap: space(4) },
  card: { gap: space(3) },
  row: { flexDirection: "row", alignItems: "center", gap: space(3), minHeight: MIN_TOUCH },
  input: {
    minHeight: MIN_TOUCH,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.chip,
    paddingHorizontal: space(3),
    color: colors.text,
    fontFamily: font.body,
    fontSize: 16,
    ...inputOutline,
  },
});
