import * as Haptics from "expo-haptics";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, View, type GestureResponderEvent } from "react-native";

import { useReducedMotion } from "../a11y";
import { useAgent } from "../agent/AgentContext";
import { colors, radius, space } from "../theme";
import { Icon, T } from "./ui";

const HOLD_MS = 500;

/**
 * Hold to talk (release sends), or tap to start and tap again to send —
 * the tap mode is what a TalkBack/VoiceOver double-tap produces.
 * It fills the space its parent gives it, so a blind user can hit it without aiming.
 * WCAG 2.5.2: sliding the finger off the button before releasing cancels the recording.
 * WCAG 2.3.3: with "reduce motion" on, the listening border is static instead of pulsing.
 */
export function TalkButton() {
  const { state, connection, startListening, stopListening, cancelListening } = useAgent();
  const reduced = useReducedMotion();
  const btn = useRef<View>(null);
  const box = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const pressedAt = useRef(0);
  const stopOnRelease = useRef(false);
  const [pulse] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (state !== "listening" || reduced) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [state, pulse, reduced]);

  const onPressIn = () => {
    btn.current?.measure((_x, _y, width, height, x, y) => (box.current = { x, y, width, height }));
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    if (state === "listening") {
      stopOnRelease.current = true;
      return;
    }
    stopOnRelease.current = false;
    pressedAt.current = Date.now();
    startListening();
  };

  const onPressOut = (e: GestureResponderEvent) => {
    // Page coordinates: locationX/Y would be relative to whichever child is under the finger.
    const { pageX, pageY } = e.nativeEvent;
    const b = box.current;
    const outside = b && (pageX < b.x || pageY < b.y || pageX > b.x + b.width || pageY > b.y + b.height);
    if (outside) {
      cancelListening(); // up reversal: finger slid off the button
      return;
    }
    if (stopOnRelease.current || Date.now() - pressedAt.current >= HOLD_MS) stopListening();
  };

  const disabled = connection !== "open";
  const label = {
    idle: "Mów",
    listening: "Słucham…",
    thinking: "Myślę…",
    speaking: "Mów", // the reply is playing; the button looks idle (you can talk over it)
  }[state];

  return (
    <View style={styles.wrap}>
      <Pressable
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        ref={btn}
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
        {state !== "thinking" ? (
          <Icon name="mic" size={110} />
        ) : null}
        <T variant="title" size={40} style={{ textAlign: "center" }}>{disabled ? "Brak połączenia" : label}</T>
      </Pressable>
      {state === "listening" ? (
        <Animated.View
          pointerEvents="none"
          style={[styles.ring, { opacity: reduced ? 1 : pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 0.2] }) }]}
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
