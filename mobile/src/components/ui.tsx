// Small building blocks: themed text, card, button.
import React from "react";
import { Pressable, StyleSheet, Text, View, type PressableProps, type TextProps, type ViewProps } from "react-native";

import { MIN_TOUCH, colors, font, radius, space } from "../theme";

type TProps = TextProps & { variant?: "body" | "title" | "number" | "muted"; size?: number; color?: string };

export function T({ variant = "body", size, color, style, ...rest }: TProps) {
  const base = {
    body: { fontFamily: font.body, fontSize: 17, color: colors.text },
    muted: { fontFamily: font.body, fontSize: 15, color: colors.textMuted },
    title: { fontFamily: font.title, fontSize: 20, color: colors.text },
    number: { fontFamily: font.number, fontSize: 28, color: colors.text },
  }[variant];
  return <Text {...rest} style={[base, size ? { fontSize: size } : null, color ? { color } : null, style]} />;
}

export function Card({ style, ...rest }: ViewProps) {
  return <View {...rest} style={[styles.card, style]} />;
}

type BtnProps = PressableProps & { label: string; kind?: "primary" | "ticket" | "outline" | "plain" };

export function Button({ label, kind = "primary", style, ...rest }: BtnProps) {
  const bg = { primary: colors.depart, ticket: colors.ticket, outline: "transparent", plain: colors.surfaceAlt }[kind];
  const fg = kind === "ticket" ? "#000" : colors.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      {...rest}
      style={(s) => [
        styles.btn,
        { backgroundColor: bg, borderWidth: kind === "outline" ? 2 : 0, opacity: s.pressed ? 0.75 : 1 },
        typeof style === "function" ? style(s) : style,
      ]}
    >
      <T variant="title" size={18} color={fg}>
        {label}
      </T>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.card, padding: space(4) },
  btn: {
    minHeight: MIN_TOUCH + 8,
    borderRadius: radius.pill,
    borderColor: colors.text,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space(5),
  },
});
