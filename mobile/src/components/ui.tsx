// Small building blocks: themed text, icon, card, button.
import { Lucide, type LucideIconName } from "@react-native-vector-icons/lucide";
import React from "react";
import { Pressable, StyleSheet, Text, View, type ColorValue, type PressableProps, type TextProps, type ViewProps } from "react-native";

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

export type IconName = LucideIconName;

/** Plain outline icon (Lucide). Always decorative: the text or label next to it says the same thing. */
export function Icon({ name, size = 20, color = colors.text }: { name: IconName; size?: number; color?: ColorValue }) {
  return (
    <Lucide
      name={name}
      size={size}
      color={color}
      importantForAccessibility="no"
      accessibilityElementsHidden
    />
  );
}

/** Icon followed by text on one line; wraps under large font scaling. */
export function IconText({
  icon,
  iconColor,
  iconSize,
  children,
  ...t
}: TProps & { icon: IconName; iconColor?: string; iconSize?: number }) {
  const size = iconSize ?? (t.size ?? (t.variant === "title" ? 20 : t.variant === "muted" ? 15 : 17)) + 2;
  return (
    <View style={styles.iconText}>
      <Icon name={icon} size={size} color={iconColor ?? t.color ?? (t.variant === "muted" ? colors.textMuted : colors.text)} />
      <T {...t} style={[{ flexShrink: 1 }, t.style]}>{children}</T>
    </View>
  );
}

/** Switch colours with a visible "off" track (WCAG 1.4.11: >= 3:1 against the card). */
export const switchColors = {
  trackColor: { true: colors.accent, false: colors.border },
  thumbColor: colors.text,
  ios_backgroundColor: colors.border,
} as const;

/** Text input outline (WCAG 1.4.11): the field's edge must be visible, not only its fill. */
export const inputOutline = { borderWidth: 2, borderColor: colors.border } as const;

export function Card({ style, ...rest }: ViewProps) {
  return <View {...rest} style={[styles.card, style]} />;
}

type BtnProps = PressableProps & { label: string; icon?: IconName; kind?: "primary" | "ticket" | "outline" | "plain" };

export function Button({ label, icon, kind = "primary", style, ...rest }: BtnProps) {
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
      {icon ? <Icon name={icon} size={20} color={fg} /> : null}
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
    flexDirection: "row",
    gap: space(2),
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: space(5),
  },
  iconText: { flexDirection: "row", alignItems: "center", gap: space(2) },
});
