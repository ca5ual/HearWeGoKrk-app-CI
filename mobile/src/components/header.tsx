import { router } from "expo-router";
import React from "react";
import { Pressable, View } from "react-native";

import { MIN_TOUCH, colors, font } from "../theme";
import { BalanceChip } from "./money";
import { T } from "./ui";

/** Right side of every header: balance chip + profile/settings. */
export function HeaderRight() {
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <BalanceChip />
      <Pressable
        onPress={() => router.push("/settings")}
        accessibilityRole="button"
        accessibilityLabel="Profil i ustawienia"
        style={{ width: MIN_TOUCH, height: MIN_TOUCH, alignItems: "center", justifyContent: "center" }}
      >
        <T size={24} importantForAccessibility="no">👤</T>
      </Pressable>
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
