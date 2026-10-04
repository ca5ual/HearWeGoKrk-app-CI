// Design tokens (dark, high contrast). Ratios checked for WCAG 2.2
// 1.4.3 (text >= 4.5:1) and 1.4.11 (UI parts >= 3:1).
export const colors = {
  bg: "#0E0E10",          // app background
  surface: "#1C1C1F",     // cards
  surfaceAlt: "#26262A",  // chips, inputs, pressed state
  text: "#FFFFFF",
  textMuted: "#A6A6AD",   // min. 4.5:1 on surface
  depart: "#0B7F56",      // primary buttons (green); white text 5.0:1
  arrive: "#1B8FD6",      // destination outline (blue); 4.8:1 on surface
  live: "#2BD69B",        // live data, on time
  delay: "#FF5C6C",       // delayed / cancelled
  accent: "#6E4FF5",      // talk button, selected segment; white text 5.1:1, 3.3:1 on surface
  accentText: "#A895FF",  // accent used as text/icon colour (active tab); 6.8:1 on surface
  border: "#8A8A93",      // input outlines, switch track; >= 4.4:1 on every surface
  ticket: "#FFC94D",      // ticket / cart actions
};
export const radius = { card: 20, chip: 12, pill: 999 };
export const space = (n: number) => n * 4;

// Manrope weights: 800 big numbers, 700 titles, 500 body.
export const font = {
  body: "Manrope_500Medium",
  title: "Manrope_700Bold",
  number: "Manrope_800ExtraBold",
};

export const MIN_TOUCH = 48;
