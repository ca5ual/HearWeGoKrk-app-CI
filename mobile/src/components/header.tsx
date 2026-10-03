import { router } from "expo-router";
import React from "react";
import { Pressable, View } from "react-native";

import { MIN_TOUCH, colors, font } from "../theme";
import { BalanceChip } from "./money";
import { Icon } from "./ui";

const iconButton = { width: MIN_TOUCH, height: MIN_TOUCH, alignItems: "center", justifyContent: "center" } as const;

/** Help is always the last item in the header, on every screen (WCAG 2.2 3.2.6 Consistent Help). */
export function HelpButton() {
  return (
    <Pressable
      onPress={() => router.push("/help")}
      accessibilityRole="button"
      accessibilityLabel="Pomoc"
      accessibilityHint="Jak korzystać z aplikacji"
      style={iconButton}
    >
      <Icon name="circle-help" size={28} />
    </Pressable>
  );
}

/** Right side of every header: balance chip, profile/settings, help. */
export function HeaderRight() {
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <BalanceChip />
      <Pressable
        onPress={() => router.push("/settings")}
        accessibilityRole="button"
        accessibilityLabel="Profil i ustawienia"
        style={iconButton}
      >
        <Icon name="circle-user" size={28} />
      </Pressable>
      <HelpButton />
    </View>
  );
}

export const headerOptions = {
  headerStyle: { backgroundColor: colors.bg },
  headerTintColor: colors.text,
  headerTitleStyle: { fontFamily: font.title, fontSize: 22 },
  headerTitleAlign: "left" as const,
  headerShadowVisible: false,
  headerRight: () => <HeaderRight />,
};
