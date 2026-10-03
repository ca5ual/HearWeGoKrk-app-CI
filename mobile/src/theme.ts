// Design tokens from FRONTEND.md section 2 (dark, high contrast).
export const colors = {
  bg: "#0E0E10",          // app background
  surface: "#1C1C1F",     // cards
  surfaceAlt: "#26262A",  // chips, inputs, pressed state
  text: "#FFFFFF",
  textMuted: "#A6A6AD",   // min. 4.5:1 on surface
  depart: "#12A36F",      // departure time chip (green)
  arrive: "#1B8FD6",      // arrival time chip (blue)
  live: "#2BD69B",        // live data, on time
  delay: "#FF5C6C",       // delayed / cancelled
  accent: "#7C5CFF",      // talk button, active tab
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
