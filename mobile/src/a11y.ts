// Accessibility helpers (WCAG 2.2: 2.3.3 Animation from Interactions, 4.1.3 Status Messages).
import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

/** True when the user turned on "remove animations" / "reduce motion" in the phone settings. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduced).catch(() => {});
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduced);
    return () => sub.remove();
  }, []);
  return reduced;
}

/** Reads a status message to TalkBack/VoiceOver when it appears or changes, without moving focus. */
export function useAnnounce(message: string | null | undefined) {
  useEffect(() => {
    if (message) AccessibilityInfo.announceForAccessibility(message);
  }, [message]);
}
