import type { LowFloor, Mode } from "./types";

/** Polish plural: 1 minuta, 2-4 minuty, 5+ minut (but 12-14 minut). */
export function minutesPl(n: number, form: "nom" | "acc" = "nom"): string {
  if (n === 1) return form === "acc" ? "minutę" : "minuta";
  if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return "minuty";
  return "minut";
}

/** "za 5 minut", "za 1 minutę", "teraz". */
export function inMinutes(n: number): string {
  return n <= 0 ? "teraz" : `za ${n} ${minutesPl(n, "acc")}`;
}

export function pricePl(p: number): string {
  return `${p.toFixed(2).replace(".", ",")} zł`;
}

export function modeName(mode: Mode): string {
  return { tram: "tramwaj", bus: "autobus", train: "pociąg" }[mode];
}

export function lowFloorLabel(lf: LowFloor | undefined): string {
  if (lf === "full") return "niskopodłogowy";
  if (lf === "partial") return "częściowo niskopodłogowy";
  if (lf === "none") return "wysokie stopnie";
  return "";
}

/** "13:28" minus N minutes -> planned time before a delay. */
export function minusMinutes(hhmm: string, n: number): string {
  const [h, m] = hhmm.split(":").map(Number);
  const t = (h * 60 + m - n + 24 * 60) % (24 * 60);
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

export function isLive(dataSource: string | undefined): boolean {
  return dataSource === "live" || dataSource === "simulated_live";
}

/** "2 przystanki", "5 przystanków". */
export function stopsPl(n: number): string {
  if (n === 1) return "1 przystanek";
  if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return `${n} przystanki`;
  return `${n} przystanków`;
}
