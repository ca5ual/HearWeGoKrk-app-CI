import { Tabs } from "expo-router/js-tabs";
import React from "react";
import type { ColorValue } from "react-native";

import { headerOptions } from "@/components/header";
import { Icon, type IconName } from "@/components/ui";
import { colors, font } from "@/theme";

const tabIcon = (name: IconName) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Icon name={name} size={24} color={color} />;
  };

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        ...headerOptions,
        sceneStyle: { backgroundColor: colors.bg },
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.surfaceAlt, minHeight: 64 },
        tabBarActiveTintColor: colors.accentText,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarLabelStyle: { fontFamily: font.title, fontSize: 13 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Mów", tabBarIcon: tabIcon("mic") }} />
      <Tabs.Screen name="route" options={{ title: "Trasa", headerShown: false, tabBarIcon: tabIcon("route") }} />
      <Tabs.Screen name="departures" options={{ title: "Rozkłady", tabBarIcon: tabIcon("clock") }} />
    </Tabs>
  );
}
