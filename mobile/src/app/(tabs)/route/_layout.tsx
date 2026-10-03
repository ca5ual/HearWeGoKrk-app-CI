import { Stack } from "expo-router";
import React from "react";

import { headerOptions } from "@/components/header";
import { colors } from "@/theme";

export default function RouteLayout() {
  return (
    <Stack screenOptions={{ ...headerOptions, contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Screen name="index" options={{ title: "Trasa" }} />
      <Stack.Screen name="results" options={{ title: "Wyniki" }} />
      <Stack.Screen name="[id]" options={{ title: "Szczegóły trasy" }} />
    </Stack>
  );
}
