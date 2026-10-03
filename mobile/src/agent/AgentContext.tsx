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

// If the server sends nothing for this long while we wait for an answer, the connection is
// probably dead (Wi-Fi dropped it silently): give up, tell the user, reconnect.
const REPLY_TIMEOUT_MS = 45000; // > a slow Claude turn (tool round + one SDK retry)
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
  const watchdog = useRef<ReturnType<typeof setTimeout> | null>(null);

  const recorder = useAudioRecorder(RECORDING_OPTIONS);

  // --- sending ------------------------------------------------------------
  /** Returns false when the socket isn't open (the message is dropped). */
  const send = useCallback((msg: object): boolean => {
    if (ws.current?.readyState !== WebSocket.OPEN) return false;
    ws.current.send(JSON.stringify(msg));
    return true;
  }, []);

  const stopWaiting = useCallback(() => {
    if (watchdog.current) clearTimeout(watchdog.current);
    watchdog.current = null;
  }, []);

  /** (Re)start the reply timeout. Every server message during a turn proves the server is alive. */
  const waitForReply = useCallback(() => {
    stopWaiting();
    watchdog.current = setTimeout(() => {
      watchdog.current = null;
      console.warn("[ws] no reply in", REPLY_TIMEOUT_MS, "ms, reconnecting");
      setState("idle");
      setNotice("Serwer nie odpowiada. Spróbuj jeszcze raz.");
      ws.current?.close(); // onclose -> reconnect
    }, REPLY_TIMEOUT_MS);
  }, [stopWaiting]);

  const notConnected = useCallback(() => {
    stopWaiting();
    setState("idle");
    setNotice("Brak połączenia z serwerem. Spróbuj za chwilę.");
  }, [stopWaiting]);

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
    if (watchdog.current) waitForReply(); // server is alive: restart the timeout
    switch (m.type) {
      case "state":
        setState(m.value);
        if (m.value === "idle") {
          stopWaiting();
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
  }, [refreshWallet, waitForReply, stopWaiting]);

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
      sock.onclose = (e) => {
        if (ws.current === sock) ws.current = null;
        console.warn(`[ws] closed (code ${e.code}${e.reason ? `, ${e.reason}` : ""}), retrying in 2 s`);
        if (watchdog.current) notConnected(); // a turn was in flight
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
  }, [backendUrl, onMessage, sendContext, refreshWallet, notConnected]);

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
    settings.current = { headphones, lang };
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
    if (send({ type: "text", text })) waitForReply();
    else notConnected();
  }, [send, waitForReply, notConnected]);

  // Recorder lifecycle. On Android the native recorder stays "prepared" until stop(), and
  // preparing it twice throws — so every transition goes through this one ref.
  const mic = useRef<"idle" | "starting" | "recording" | "stopping">("idle");
  const stopRequested = useRef(false); // button released while the recorder was still starting

  const micFailed = useCallback((what: string, e: unknown) => {
    console.warn(`[audio] ${what}:`, e);
    mic.current = "idle";
    setState("idle");
    setNotice("Nie udało się nagrać. Spróbuj jeszcze raz.");
  }, []);

  /** Stop the native recorder if it is prepared or recording (ignores "not recording" errors). */
  const resetRecorder = useCallback(async () => {
    const st = recorder.getStatus();
    if (st.isRecording || st.canRecord) {
      try {
        await recorder.stop();
      } catch {}
    }
  }, [recorder]);

  const stopListening = useCallback(async () => {
    if (mic.current === "starting") {
      stopRequested.current = true; // startListening finishes, then calls us again
      return;
    }
    if (mic.current !== "recording") return;
    mic.current = "stopping";
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch (e) {
      return micFailed("stop failed", e);
    }
    mic.current = "idle";
    setState("thinking");
    const uri = recorder.uri;
    if (!uri) return setState("idle");
    try {
      for (const data of await recordingToChunks(uri)) {
        if (!send({ type: "audio_chunk", data })) return notConnected();
      }
    } catch (e) {
      console.warn("[audio] could not read the recording:", e);
      setState("idle");
      return setNotice("Nie udało się nagrać. Spróbuj jeszcze raz.");
    }
    if (send({ type: "end_of_speech" })) waitForReply();
    else notConnected();
  }, [recorder, send, waitForReply, notConnected, micFailed]);

  const startListening = useCallback(async () => {
    if (mic.current !== "idle") return; // a second press while starting/stopping: ignore
    mic.current = "starting";
    stopRequested.current = false;
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        mic.current = "idle";
        setNotice("Potrzebuję dostępu do mikrofonu (Ustawienia telefonu → Aplikacje → Expo Go).");
        return;
      }
      beginTurn();
      await resetRecorder(); // left prepared by an earlier failure? start clean
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) {
      await resetRecorder();
      return micFailed("could not start recording", e);
    }
    mic.current = "recording";
    setState("listening");
    if (stopRequested.current) stopListening(); // released during the permission dialog / prepare
  }, [recorder, resetRecorder, micFailed, stopListening]);

  const stop = useCallback(() => {
    beginTurn();
    if (send({ type: "stop" })) waitForReply();
    else notConnected();
  }, [send, waitForReply, notConnected]);

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
