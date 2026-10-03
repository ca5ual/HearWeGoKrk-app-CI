import { Tabs } from "expo-router/js-tabs";
import React from "react";

import { headerOptions } from "@/components/header";
import { T } from "@/components/ui";
import { colors, font } from "@/theme";

const icon = (glyph: string) => () => <T size={22} importantForAccessibility="no">{glyph}</T>;

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        ...headerOptions,
        sceneStyle: { backgroundColor: colors.bg },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.surfaceAlt, minHeight: 64 },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontFamily: font.title, fontSize: 13 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Mów", tabBarIcon: icon("🎙") }} />
      <Tabs.Screen name="route" options={{ title: "Trasa", headerShown: false, tabBarIcon: icon("🧭") }} />
      <Tabs.Screen name="departures" options={{ title: "Rozkłady", tabBarIcon: icon("🕑") }} />
      <Tabs.Screen name="tickets" options={{ title: "Bilety", tabBarIcon: icon("🎫") }} />
    </Tabs>
  );
}
