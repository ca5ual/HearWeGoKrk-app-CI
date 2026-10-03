// REST calls (README 4.3). Everything spoken goes over the WebSocket; these feed the companion screens.
import type { Departure, RouteResult, Stop, Wallet } from "./types";

async function req<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}

export const api = {
  stops: (b: string) => req<Stop[]>(b, "/stops"),
  departures: (b: string, stopId: string, limit = 8) =>
    req<Departure[]>(b, `/stops/${encodeURIComponent(stopId)}/departures?limit=${limit}`),
  route: (b: string, destination: string, preferLowFloor?: boolean) =>
    req<RouteResult>(b, "/route", {
      method: "POST",
      body: JSON.stringify({ destination, prefer_low_floor: preferLowFloor }),
    }),
  wallet: (b: string) => req<Wallet>(b, "/wallet"),
  demoReset: (b: string, offsetMin = 0) =>
    req(b, "/demo/reset", { method: "POST", body: JSON.stringify({ offset_min: offsetMin }) }),
  demoClock: (b: string, offsetMin: number) =>
    req(b, "/demo/clock", { method: "POST", body: JSON.stringify({ offset_min: offsetMin }) }),
  demoGps: (b: string, sideNumber: string) =>
    req(b, "/demo/gps", { method: "POST", body: JSON.stringify({ side_number: sideNumber }) }),
  demoGpsClear: (b: string) => req(b, "/demo/gps", { method: "DELETE" }),
};
