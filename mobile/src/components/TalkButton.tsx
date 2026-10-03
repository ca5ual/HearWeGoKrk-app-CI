import * as Haptics from "expo-haptics";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, View } from "react-native";

import { useAgent } from "../agent/AgentContext";
import { colors, radius, space } from "../theme";
import { T } from "./ui";

const HOLD_MS = 500;

/**
 * Hold to talk (release sends), or tap to start and tap again to send —
 * the tap mode is what a TalkBack/VoiceOver double-tap produces.
 * It fills the space its parent gives it, so a blind user can hit it without aiming.
 */
export function TalkButton() {
  const { state, connection, startListening, stopListening } = useAgent();
  const pressedAt = useRef(0);
  const stopOnRelease = useRef(false);
  const [pulse] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (state !== "listening") return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [state, pulse]);

  const onPressIn = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    if (state === "listening") {
      stopOnRelease.current = true;
      return;
    }
    stopOnRelease.current = false;
    pressedAt.current = Date.now();
    startListening();
  };

  const onPressOut = () => {
    if (stopOnRelease.current || Date.now() - pressedAt.current >= HOLD_MS) stopListening();
  };

  const disabled = connection !== "open";
  const label = {
    idle: "Mów",
    listening: "Słucham…",
    thinking: "Myślę…",
    speaking: "Mówię…",
  }[state];

  return (
    <View style={styles.wrap}>
      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="Mów do asystenta"
        accessibilityHint={
          state === "listening" ? "Stuknij, aby wysłać" : "Przytrzymaj i mów, albo stuknij, aby zacząć"
        }
        accessibilityState={{ disabled, busy: state === "thinking" }}
        style={({ pressed }) => [styles.button, { opacity: disabled ? 0.4 : pressed ? 0.85 : 1 }]}
      >
        {state === "thinking" ? <ActivityIndicator size="large" color={colors.text} style={{ transform: [{ scale: 2 }] }} /> : null}
        {state === "speaking" ? <T size={64} importantForAccessibility="no">▂▅▇▅▂</T> : null}
        {state === "idle" || state === "listening" ? (
          <T size={110} style={{ lineHeight: 130 }} importantForAccessibility="no">🎙</T>
        ) : null}
        <T variant="title" size={40} style={{ textAlign: "center" }}>{disabled ? "Brak połączenia" : label}</T>
      </Pressable>
      {state === "listening" ? (
        <Animated.View
          pointerEvents="none"
          style={[styles.ring, { opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 0.2] }) }]}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, alignSelf: "stretch" },
  ring: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    borderRadius: radius.card * 2,
    borderWidth: 10,
    borderColor: colors.text,
  },
  button: {
    flex: 1,
    borderRadius: radius.card * 2,
    backgroundColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
    gap: space(3),
    padding: space(4),
  },
});
