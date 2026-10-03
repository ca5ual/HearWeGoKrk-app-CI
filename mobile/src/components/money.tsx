// Money-related UI: balance chip (header), TicketFab, the confirmation modal (FRONTEND.md 5.7).
import React, { useEffect, useState } from "react";
import { Modal, Pressable, StyleSheet, View } from "react-native";

import { useReducedMotion } from "../a11y";
import { useAgent, type Pending } from "../agent/AgentContext";
import { pricePl } from "../format";
import { MIN_TOUCH, colors, radius, space } from "../theme";
import { Button, Card, Icon, T } from "./ui";

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
  const { confirmPending, cancelPending, extendPending, wallet } = useAgent();
  const reduced = useReducedMotion();
  const [now, setNow] = useState(() => Date.now());
  const [showPrice, setShowPrice] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  const d = pending.data;
  const left = Math.max(0, Math.ceil(pending.timeoutS - (now - pending.receivedAt) / 1000));
  const priceVisible = d.show_price || showPrice;
  const payment = d.payment_source === "balance" ? "Z salda w aplikacji" : wallet?.default_card ?? "Domyślna karta";

  return (
    <Modal visible transparent animationType={reduced ? "none" : "slide"} onRequestClose={cancelPending}>
      <View style={styles.backdrop}>
        <Card style={styles.sheet} accessibilityViewIsModal>
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

          <T variant="muted" accessibilityLiveRegion="none">
            {left > 0 ? `Czekam na odpowiedź: ${left} s` : "Nie usłyszałem odpowiedzi — powiedz tak albo nie"}
          </T>

          <Button kind="ticket" icon="check" label="Potwierdź" onPress={confirmPending} />
          <Button kind="outline" icon="x" label="Anuluj" onPress={cancelPending} />
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
    </Modal>
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
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  sheet: { gap: space(4), borderBottomLeftRadius: 0, borderBottomRightRadius: 0, paddingBottom: space(10) },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space(3) },
});
