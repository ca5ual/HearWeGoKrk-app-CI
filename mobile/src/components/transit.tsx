// Shared transit pieces: LineBox, LowFloorNote, LiveIndicator. Words over symbols: every
// colour or icon is paired with text that says the same thing.
import React from "react";
import { StyleSheet, View } from "react-native";

import { lowFloorLabel, modeName } from "../format";
import { colors, radius, space } from "../theme";
import type { LowFloor, Mode } from "../types";
import { IconText, T, type IconName } from "./ui";

export const MODE_ICON: Record<Mode, IconName> = { tram: "tram-front", bus: "bus-front", train: "train-front" };

/** "Tramwaj", "Autobus", "Pociąg". */
export const modeTitle = (mode: Mode) => {
  const n = modeName(mode);
  return n[0].toUpperCase() + n.slice(1);
};

/** Big line number with the mode written under it. Decorative: the row's label says it. */
export function LineBox({ mode, number }: { mode: Mode; number: string }) {
  return (
    <View style={styles.lineBox} importantForAccessibility="no-hide-descendants">
      <T variant="number" size={24} style={{ lineHeight: 28 }}>{number}</T>
      <T variant="muted" size={12}>{modeName(mode)}</T>
    </View>
  );
}

export function LowFloorNote({ lowFloor, size = 14 }: { lowFloor?: LowFloor; size?: number }) {
  if (!lowFloor) return null;
  const none = lowFloor === "none";
  return (
    <IconText size={size} icon={none ? "triangle-alert" : "accessibility"} color={none ? colors.delay : colors.live}>
      {lowFloorLabel(lowFloor)}
    </IconText>
  );
}

export function LiveIndicator({ dataSource, delayed }: { dataSource?: string; delayed?: boolean }) {
  const live = dataSource === "live" || dataSource === "simulated_live";
  if (!live) {
    return (
      <IconText variant="muted" size={13} icon="clock" accessibilityLabel="według rozkładu">
        według rozkładu
      </IconText>
    );
  }
  return (
    <IconText
      size={13}
      icon="radio"
      color={delayed ? colors.delay : colors.live}
      accessibilityLabel={delayed ? "dane na żywo, opóźniony" : "dane na żywo"}
    >
      na żywo
    </IconText>
  );
}

const styles = StyleSheet.create({
  lineBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.chip,
    minWidth: 64,
    paddingHorizontal: space(2),
    paddingVertical: space(2),
    alignItems: "center",
  },
});
