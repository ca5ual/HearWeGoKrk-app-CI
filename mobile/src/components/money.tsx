// Money-related UI: balance chip (header), TicketFab, the confirmation modal (FRONTEND.md 5.7).
import * as Haptics from "expo-haptics";
import React, { useEffect, useRef, useState } from "react";
import { BackHandler, Pressable, StyleSheet, View } from "react-native";

import { useAgent, type Pending } from "../agent/AgentContext";
import { pricePl } from "../format";
import { MIN_TOUCH, colors, radius, space } from "../theme";
import { Button, Card, Icon, IconText, T } from "./ui";

/** Without headphones the amount stays hidden (TalkBack would read it aloud); tap shows it for 5 s. */
export function BalanceChip() {
  const { wallet, headphones } = useAgent();
  const [reveal, setReveal] = useState(false);
  useEffect(() => {
    if (!reveal) return;
    const t = setTimeout(() => setReveal(false), 5000);
    return () => clearTimeout(t);
  }, [reveal]);
  if (!wallet) return null;
  const show = headphones || reveal;
  return (
    <Pressable
      onPress={() => setReveal(true)}
      accessibilityRole="button"
      accessibilityLabel={show ? `Saldo ${wallet.balance_text}` : "Saldo ukryte. Stuknij, aby pokazać"}
      style={styles.chip}
    >
      <T variant="title" size={15}>{show ? wallet.balance_text : "•••• zł"}</T>
    </Pressable>
  );
}

/** Floating cart button. Buying always goes through the agent -> prepare_ticket -> modal. */
export function TicketFab({ price }: { price?: number }) {
  const { sendText, headphones, connection } = useAgent();
  return (
    <View style={styles.fabRow} pointerEvents="box-none">
      {price != null && headphones ? (
        <View style={styles.fabPill} importantForAccessibility="no-hide-descendants">
          <T variant="title" size={15}>Kup bilet · {pricePl(price)}</T>
        </View>
      ) : null}
      <Pressable
        onPress={() => sendText("kup bilet")}
        disabled={connection !== "open"}
        accessibilityRole="button"
        accessibilityLabel="Kup bilet"
        accessibilityHint="Asystent przygotuje bilet i poprosi o potwierdzenie"
        style={({ pressed }) => [styles.fab, { opacity: pressed ? 0.8 : 1 }]}
      >
        <Icon name="shopping-cart" size={28} color="#000" />
      </Pressable>
    </View>
  );
}

export function ConfirmModal() {
  const { pending } = useAgent();
  // key: a new purchase gets fresh state (price hidden again, new countdown).
  return pending ? <ConfirmSheet key={pending.id} pending={pending} /> : null;
}

function ConfirmSheet({ pending }: { pending: Pending }) {
  const { confirmPending, cancelPending, extendPending, answerNow, stopListening, wallet, state } = useAgent();
  const [now, setNow] = useState(() => Date.now());
  const [showPrice, setShowPrice] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  // Android back = Anuluj (what the old Modal's onRequestClose did).
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      cancelPending();
      return true;
    });
    return () => sub.remove();
  }, [cancelPending]);

  const d = pending.data;
  // The window starts when the phone opens the mic after the question (receivedAt is reset then);
  // while the question is read or the answer checked, the clock stands still on the server too.
  const paused = state === "speaking" || state === "thinking";
  const left = paused
    ? pending.timeoutS
    : Math.max(0, Math.ceil(pending.timeoutS - (now - pending.receivedAt) / 1000));
  const urgent = !paused && left <= 5;

  // Felt, not spoken: a screen-reader announcement would land in the open mic.
  const buzzed = useRef<number | null>(null);
  useEffect(() => {
    if (paused || (left !== 10 && left !== 5) || buzzed.current === left) return;
    buzzed.current = left;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  }, [left, paused]);
  const priceVisible = d.show_price || showPrice;
  const payment = d.payment_source === "balance" ? "Z salda w aplikacji" : wallet?.default_card ?? "Domyślna karta";

  return (
    // Not a Modal: a modal blocks the screen behind it, and the user must still be able to reach
    // the big Mów button. The phone also listens by itself after the question (AgentContext).
    <View style={styles.overlay} pointerEvents="box-none">
        <Card style={styles.sheet}>
          <T variant="muted" accessibilityRole="header">Potwierdź zakup</T>
          <T variant="title" size={24}>{d.ticket.name_pl}</T>

          <View style={styles.row}>
            <T variant="muted">Pojazd</T>
            <T variant="number" size={40} accessibilityLabel={`pojazd ${d.side_number?.split("").join(" ")}`}>
              {d.side_number ?? "—"}
            </T>
          </View>

          <View style={styles.row}>
            <T variant="muted">Cena</T>
            {priceVisible ? (
              <T variant="number" size={28}>{pricePl(d.ticket.price_pln)}</T>
            ) : (
              <Button kind="plain" label="Pokaż kwotę" onPress={() => setShowPrice(true)} />
            )}
          </View>

          <View style={styles.row}>
            <T variant="muted">Płatność</T>
            <T variant="title" size={17} style={{ flexShrink: 1, textAlign: "right" }}>{payment}</T>
          </View>

          <View
            style={styles.timer}
            accessible
            accessibilityRole="timer"
            accessibilityLabel={
              paused ? `Czas na odpowiedź: ${pending.timeoutS} sekund, liczy się po pytaniu` : `Zostało ${left} sekund na odpowiedź`
            }
          >
            <View style={styles.row}>
              <IconText icon="timer" variant="muted">{paused ? "Czas na odpowiedź (start po pytaniu)" : "Zostało na odpowiedź"}</IconText>
              <T variant="number" size={36} color={urgent ? colors.delay : colors.text}>{left} s</T>
            </View>
            <View style={styles.track}>
              <View
                style={[
                  styles.bar,
                  { width: `${(100 * left) / pending.timeoutS}%`, backgroundColor: urgent ? colors.delay : colors.ticket },
                ]}
              />
            </View>
          </View>

          {state === "speaking" ? (
            // Barge-in: no need to wait for the question to finish.
            <Button kind="primary" icon="mic" label="Przerwij i odpowiedz" onPress={answerNow}
              accessibilityHint="Zatrzymuje czytanie i od razu słucha, czy powiesz tak albo nie" />
          ) : null}

          {state === "listening" ? (
            // The phone sends by itself when you go quiet; this is the manual "done".
            <Button kind="primary" icon="send" label="Wyślij odpowiedź" onPress={stopListening}
              accessibilityHint="Kończy nagrywanie i wysyła, co powiedziałeś" />
          ) : null}

          <View style={styles.row} accessibilityLiveRegion="polite">
            <Icon name={state === "listening" ? "mic" : "mic-off"} size={22} />
            <T variant="title" size={17} style={{ flex: 1 }}>
              {state === "listening"
                ? "Słucham — powiedz „tak” albo „nie”"
                : state === "speaking"
                  ? "Czytam pytanie…"
                : state === "thinking"
                  ? "Sprawdzam odpowiedź…"
                  : left > 0
                    ? "Powiedz „tak” albo „nie”"
                    : "Nie usłyszałem — powiedz „tak” albo „nie”"}
            </T>
          </View>

          <View style={styles.buttons}>
            <Button kind="ticket" icon="check" label="Potwierdź" onPress={confirmPending} style={{ flex: 1 }} />
            <Button kind="outline" icon="x" label="Anuluj" onPress={cancelPending} style={{ flex: 1 }} />
          </View>
          {/* WCAG 2.2.1 Timing Adjustable: one tap restarts the window; it never confirms. */}
          <Button
            kind="plain"
            icon="timer-reset"
            label="Potrzebuję więcej czasu"
            accessibilityHint="Wydłuża czas na decyzję. Zakup nadal wymaga potwierdzenia."
            onPress={extendPending}
          />
        </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: space(3),
    minHeight: MIN_TOUCH - 8,
    justifyContent: "center",
    marginRight: space(2),
  },
  fabRow: {
    position: "absolute",
    right: space(4),
    bottom: space(4),
    flexDirection: "row",
    alignItems: "center",
    gap: space(2),
  },
  fabPill: { backgroundColor: "#000", borderRadius: radius.pill, paddingHorizontal: space(4), paddingVertical: space(2) },
  fab: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.ticket,
    alignItems: "center",
    justifyContent: "center",
  },
  overlay: { position: "absolute", top: 0, right: 0, bottom: 0, left: 0, justifyContent: "flex-end" },
  sheet: {
    gap: space(3),
    borderBottomLeftRadius: 0,
    borderBottomRightRadius: 0,
    paddingBottom: space(6),
    borderTopWidth: 2,
    borderColor: colors.ticket,
  },
  buttons: { flexDirection: "row", gap: space(3) },
  timer: { gap: space(2) },
  track: { height: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceAlt, overflow: "hidden" },
  bar: { height: "100%", borderRadius: radius.pill },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(3) },
});
