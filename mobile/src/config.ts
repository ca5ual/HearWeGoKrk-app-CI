import Constants from "expo-constants";

/**
 * Backend base URL (http://<laptop-ip>:8000).
 * 1. EXPO_PUBLIC_BACKEND_URL from mobile/.env, if set.
 * 2. Otherwise the laptop running `expo start` (same host, port 8000) — works on the same WiFi.
 * Can also be changed at runtime in Ustawienia.
 */
export function defaultBackendUrl(): string {
  const env = process.env.EXPO_PUBLIC_BACKEND_URL;
  if (env) return env.replace(/\/$/, "");
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  return `http://${host ?? "localhost"}:8000`;
}

export function wsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/, "ws") + "/ws/voice";
}
