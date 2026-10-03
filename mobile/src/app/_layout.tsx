import {
  Manrope_500Medium,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from "@expo-google-fonts/manrope";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import React from "react";

import { AgentProvider } from "@/agent/AgentContext";
import { HelpButton, headerOptions } from "@/components/header";
import { ConfirmModal } from "@/components/money";
import { colors } from "@/theme";

export default function RootLayout() {
  const [loaded, error] = useFonts({ Manrope_500Medium, Manrope_700Bold, Manrope_800ExtraBold });
  if (!loaded && !error) return null;

  return (
    <AgentProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ ...headerOptions, contentStyle: { backgroundColor: colors.bg } }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="trip" options={{ title: "Jedziesz" }} />
        <Stack.Screen name="settings" options={{ title: "Ustawienia", presentation: "modal", headerRight: () => <HelpButton /> }} />
        <Stack.Screen name="help" options={{ title: "Pomoc", presentation: "modal", headerRight: undefined }} />
      </Stack>
      {/* Every action that costs money goes through this modal (FRONTEND.md 5.7). */}
      <ConfirmModal />
    </AgentProvider>
  );
}
