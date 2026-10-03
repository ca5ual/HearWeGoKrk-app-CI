/**
 * AgentContext — the /ws/voice connection (README 4.2) and everything the screens read from it:
 * agent state, transcript, reply, the latest `ui` payload per component, the pending purchase, the trip.
 */
import {
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { defaultBackendUrl, wsUrl } from "../config";
import type { AgentState, PreparedTicket, RouteResult, TripStatus, UiPayload, Wallet } from "../types";
import {
  RECORDING_OPTIONS,
  forgetLastAudio,
  playReplyAudio,
  recordingToChunks,
  replayLast,
  speakText,
  stopPlayback,
} from "./audio";
import { watchLocation, type Coords } from "./location";

type Component = UiPayload["component"];
type UiData = { [K in Component]?: Extract<UiPayload, { component: K }>["data"] };

export type Pending = { id: string; timeoutS: number; data: PreparedTicket; receivedAt: number };

type Connection = "connecting" | "open" | "closed";

type AgentCtx = {
  backendUrl: string;
  setBackendUrl: (u: string) => void;
  connection: Connection;
  state: AgentState;
  transcript: string;
  replyText: string;
  lastUi: UiPayload | null;
  ui: UiData;
  setRouteResult: (r: RouteResult) => void;
  pending: Pending | null;
  notice: string | null;               // short one-off message, e.g. "Nie kupiono biletu"
  trip: TripStatus | null;
  wallet: Wallet | null;
  refreshWallet: () => void;
  headphones: boolean;
  setHeadphones: (v: boolean) => void;
  lang: "pl" | "en";
  setLang: (l: "pl" | "en") => void;
  sendText: (text: string) => void;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
  stop: () => void;
  confirmPending: () => void;
  cancelPending: () => void;
  replay: () => void;
};

const Ctx = createContext<AgentCtx | null>(null);

export function useAgent(): AgentCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAgent outside AgentProvider");
  return c;
}

// Which tab shows which `ui` component. ticket_confirm is the modal, driven by `pending`.
const SCREEN_FOR: Partial<Record<Component, string>> = {
  route_results: "/route/results",
  departures: "/departures",
  ticket_shop: "/tickets",
  trip_live: "/trip",
};

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const [backendUrl, setBackendUrl] = useState(defaultBackendUrl);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [state, setState] = useState<AgentState>("idle");
  const [transcript, setTranscript] = useState("");
  const [replyText, setReplyText] = useState("");
  const [ui, setUi] = useState<UiData>({});
  const [lastUi, setLastUi] = useState<UiPayload | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [trip, setTrip] = useState<TripStatus | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [headphones, setHeadphones] = useState(false); // no headphone detection in Expo Go: privacy-safe default
  const [lang, setLang] = useState<"pl" | "en">("pl");

  const ws = useRef<WebSocket | null>(null);
  const coords = useRef<Coords | null>(null);
  const userTurn = useRef(false);            // between our utterance and the next idle: navigate on `ui`
  const reply = useRef<{ text: string; chunks: string[] } | null>(null);
  const settings = useRef({ headphones, lang });
  settings.current = { headphones, lang };

  const recorder = useAudioRecorder(RECORDING_OPTIONS);

  // --- sending ------------------------------------------------------------
  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
  }, []);

  const sendContext = useCallback(() => {
    send({
      type: "context",
      ...(coords.current ? { lat: coords.current.lat, lon: coords.current.lon } : {}),
      headphones: settings.current.headphones,
      lang: settings.current.lang,
    });
  }, [send]);

  const refreshWallet = useCallback(() => {
    api.wallet(backendUrl).then(setWallet).catch(() => {});
  }, [backendUrl]);

  // --- incoming -------------------------------------------------------------
  const onMessage = useCallback((raw: string) => {
    let m: any;
    try {
      m = JSON.parse(raw);
    } catch {
      return;
    }
    switch (m.type) {
      case "state":
        setState(m.value);
        if (m.value === "idle") {
          const r = reply.current;
          reply.current = null;
          if (r) {
            if (r.chunks.length) playReplyAudio(r.chunks);
            else speakText(r.text, settings.current.lang); // backend TTS not wired yet -> phone voice
          }
          userTurn.current = false;
        }
        break;
      case "transcript":
        setTranscript(m.text);
        break;
      case "reply_text":
        setReplyText(m.text);
        forgetLastAudio();
        reply.current = { text: m.text, chunks: [] };
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        break;
      case "audio_chunk":
        reply.current?.chunks.push(m.data);
        break;
      case "haptic":
        if (m.pattern === "confirm") {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          setPending(null); // purchase done
          refreshWallet();
        } else if (m.pattern === "warning") {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        } else if (m.pattern === "arrived") {
          [0, 250, 500].forEach((t) => setTimeout(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy), t));
        }
        break;
      case "ui": {
        const p = m as UiPayload;
        setUi((u) => ({ ...u, [p.component]: p.data }));
        if (p.component === "trip_live") setTrip(p.data);
        if (p.component !== "ticket_confirm") setLastUi(p);
        const screen = SCREEN_FOR[p.component];
        // Navigate only for results the user asked for, not for background trip updates.
        if (screen && userTurn.current) router.navigate(screen as any);
        break;
      }
      case "pending_confirmation":
        setNotice(null);
        setPending({ id: m.id, timeoutS: m.timeout_s, data: m.data, receivedAt: Date.now() });
        break;
      case "pending_cancelled":
        setPending((p) => (p && p.id === m.id ? null : p));
        setNotice("Nie kupiono biletu");
        break;
      case "error":
        console.warn("[ws] server error:", m.message);
        break;
      // "session": nothing to do
    }
  }, [refreshWallet]);

  // --- connection with auto-reconnect ---------------------------------------
  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      setConnection("connecting");
      const sock = new WebSocket(wsUrl(backendUrl));
      ws.current = sock;
      sock.onopen = () => {
        setConnection("open");
        sendContext();
      };
      sock.onmessage = (e) => onMessage(String(e.data));
      sock.onclose = () => {
        if (ws.current === sock) ws.current = null;
        setConnection("closed");
        setState("idle");
        if (!closed) retry = setTimeout(connect, 2000);
      };
      sock.onerror = () => sock.close();
    };
    connect();
    refreshWallet();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws.current?.close();
    };
  }, [backendUrl, onMessage, sendContext, refreshWallet]);

  // GPS + settings -> context message.
  useEffect(() => {
    let unsub = () => {};
    watchLocation((c) => {
      coords.current = c;
      sendContext();
    }).then((u) => (unsub = u)).catch(() => {});
    return () => unsub();
  }, [sendContext]);

  useEffect(() => {
    sendContext();
  }, [headphones, lang, sendContext]);

  // Client-side safety net: the backend hard-expires a purchase after 2 * timeout + 5 s.
  // (It does not announce a voice "nie", so this also closes a modal left open after one.)
  useEffect(() => {
    if (!pending) return;
    const ms = (pending.timeoutS * 2 + 5) * 1000 - (Date.now() - pending.receivedAt);
    const t = setTimeout(() => setPending((p) => (p?.id === pending.id ? null : p)), Math.max(0, ms));
    return () => clearTimeout(t);
  }, [pending]);

  // --- actions --------------------------------------------------------------
  const beginTurn = () => {
    userTurn.current = true;
    stopPlayback();
    setNotice(null);
  };

  const sendText = useCallback((text: string) => {
    if (!text.trim()) return;
    beginTurn();
    send({ type: "text", text });
  }, [send]);

  const startListening = useCallback(async () => {
    const perm = await requestRecordingPermissionsAsync();
    if (!perm.granted) return;
    beginTurn();
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
    setState("listening");
  }, [recorder]);

  const stopListening = useCallback(async () => {
    if (!recorder.isRecording) return;
    await recorder.stop();
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    setState("thinking");
    const uri = recorder.uri;
    if (!uri) return setState("idle");
    for (const data of await recordingToChunks(uri)) send({ type: "audio_chunk", data });
    send({ type: "end_of_speech" });
  }, [recorder, send]);

  const stop = useCallback(() => {
    beginTurn();
    send({ type: "stop" });
  }, [send]);

  // Modal buttons. README 4.2 has no "confirm" message yet, so the button says "tak" as text —
  // exactly what the voice path does. "Anuluj" uses the README `stop` message.
  const confirmPending = useCallback(() => sendText("tak"), [sendText]);
  const cancelPending = useCallback(() => {
    setPending(null);
    stop();
  }, [stop]);

  const replay = useCallback(() => replayLast(replyText, settings.current.lang), [replyText]);

  const setRouteResult = useCallback((r: RouteResult) => {
    setUi((u) => ({ ...u, route_results: r }));
  }, []);

  const value = useMemo<AgentCtx>(
    () => ({
      backendUrl, setBackendUrl, connection, state, transcript, replyText, lastUi, ui, setRouteResult,
      pending, notice, trip, wallet, refreshWallet, headphones, setHeadphones, lang, setLang,
      sendText, startListening, stopListening, stop, confirmPending, cancelPending, replay,
    }),
    [backendUrl, connection, state, transcript, replyText, lastUi, ui, setRouteResult, pending, notice, trip,
      wallet, refreshWallet, headphones, lang, sendText, startListening, stopListening, stop, confirmPending,
      cancelPending, replay],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
