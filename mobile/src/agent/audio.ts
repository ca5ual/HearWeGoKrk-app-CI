/**
 * audio.ts — recording format, base64 helpers, reply playback.
 *
 * Contract (README 4.2): audio_chunk = base64 PCM16, 16 kHz, mono.
 *  - iOS: expo-audio records LINEARPCM into a .wav; we strip the WAV header and send raw PCM16.
 *  - Android: expo-audio can't record PCM (only AAC/AMR), so we send the AAC (.m4a) bytes.
 *    The backend must detect/decode that (the file starts with "....ftyp"). Agreed with Person A? -> see PR notes.
 */
import { AudioQuality, IOSOutputFormat, createAudioPlayer, type AudioPlayer, type RecordingOptions } from "expo-audio";
import { File, Paths } from "expo-file-system";
import * as Speech from "expo-speech";
import { Platform } from "react-native";

export const RECORDING_OPTIONS: RecordingOptions = {
  extension: Platform.OS === "ios" ? ".wav" : ".m4a",
  sampleRate: 16000,
  numberOfChannels: 1,
  isMeteringEnabled: true, // hands-free answers: stop recording when the user goes quiet
  bitRate: 256000,
  android: { outputFormat: "mpeg4", audioEncoder: "aac" },
  ios: {
    outputFormat: IOSOutputFormat.LINEARPCM,
    audioQuality: AudioQuality.MAX,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: { mimeType: "audio/webm" },
};

// --- base64 (no Buffer in React Native) --------------------------------------
const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

export function bytesToBase64(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const n = (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63];
    out += i + 1 < bytes.length ? B64[(n >> 6) & 63] : "=";
    out += i + 2 < bytes.length ? B64[n & 63] : "=";
  }
  return out;
}

export function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, "");
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const n =
      (B64.indexOf(clean[i]) << 18) |
      (B64.indexOf(clean[i + 1]) << 12) |
      ((B64.indexOf(clean[i + 2] ?? "A") & 63) << 6) |
      (B64.indexOf(clean[i + 3] ?? "A") & 63);
    out[o++] = (n >> 16) & 255;
    if (i + 2 < clean.length) out[o++] = (n >> 8) & 255;
    if (i + 3 < clean.length) out[o++] = n & 255;
  }
  return out.subarray(0, o);
}

/** Return the samples of the WAV "data" chunk (raw PCM16), or the input if it's not a WAV. */
function wavToPcm(bytes: Uint8Array): Uint8Array {
  const tag = (o: number) => String.fromCharCode(bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]);
  if (bytes.length < 12 || tag(0) !== "RIFF" || tag(8) !== "WAVE") return bytes;
  let o = 12;
  while (o + 8 <= bytes.length) {
    // >>> 0: unsigned. A signed size could be negative and make this loop run forever.
    const size = (bytes[o + 4] | (bytes[o + 5] << 8) | (bytes[o + 6] << 16) | (bytes[o + 7] << 24)) >>> 0;
    if (tag(o) === "data") return bytes.subarray(o + 8, Math.min(bytes.length, o + 8 + size));
    o += 8 + size + (size % 2);
  }
  return bytes;
}

/** Read a finished recording and split it into base64 audio_chunk payloads (~1 s each). */
export async function recordingToChunks(uri: string, chunkBytes = 32000): Promise<string[]> {
  const file = new File(uri);
  const audio = wavToPcm(await file.bytes());
  const chunks: string[] = [];
  for (let i = 0; i < audio.length; i += chunkBytes) chunks.push(bytesToBase64(audio.subarray(i, i + chunkBytes)));
  try {
    file.delete();
  } catch {}
  return chunks;
}

// --- playback ----------------------------------------------------------------
let player: AudioPlayer | null = null;
let lastReplyFile: File | null = null;

export function stopPlayback(): void {
  player?.pause();
  player?.remove();
  player = null;
  Speech.stop();
}

/** Play the server's TTS (the audio_chunk messages of one reply, concatenated). */
export function playReplyAudio(chunks: string[], onDone?: () => void): void {
  const parts = chunks.map(base64ToBytes);
  const all = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) {
    all.set(p, o);
    o += p.length;
  }
  try {
    lastReplyFile?.delete();
  } catch {}
  const file = new File(Paths.cache, `reply-${Date.now()}.mp3`);
  file.create();
  file.write(all);
  lastReplyFile = file;
  replayLast(undefined, "pl", onDone);
}

/** Fallback while the backend sends no TTS audio: speak with the phone's own voice. */
export function speakText(text: string, lang: "pl" | "en", onDone?: () => void): void {
  stopPlayback();
  Speech.speak(text, { language: lang === "pl" ? "pl-PL" : "en-US", onDone });
}

/** "Powtórz": replay the last audio reply, or re-speak the text if there was no audio. */
export function replayLast(fallbackText?: string, lang: "pl" | "en" = "pl", onDone?: () => void): void {
  if (lastReplyFile?.exists) {
    stopPlayback();
    const p = createAudioPlayer(lastReplyFile.uri);
    player = p;
    if (onDone) {
      const sub = p.addListener("playbackStatusUpdate", (s) => {
        if (!s.didJustFinish) return;
        sub.remove();
        if (player === p) onDone(); // not when it was interrupted by a newer reply
      });
    }
    p.play();
  } else if (fallbackText) {
    speakText(fallbackText, lang, onDone);
  }
}

export function forgetLastAudio(): void {
  try {
    lastReplyFile?.delete();
  } catch {}
  lastReplyFile = null;
}
