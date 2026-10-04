import { useEffect, useRef, useState } from "react";

const GREETINGS = "hey|hi|hello|hiya|yo|howdy|okay|ok|hey there|hi there";

/** Words a child might call the plant: its full name and each longer word in it. */
export function wakePattern(name: string): RegExp {
  const words = name.toLowerCase().replace(/[^a-z\s]/g, " ").split(/\s+/).filter(Boolean);
  const names = [words.join("\\s+"), ...words.filter((w) => w.length >= 3)].filter(Boolean);
  return new RegExp(`\\b(${GREETINGS})\\b[\\s,!.]*(${names.join("|")})\\b`, "i");
}

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  abort: () => void;
};

/**
 * Listens for "Hi <plant name>" with the browser's speech recognition (Chrome/Edge) and
 * calls onWake. Paused while `enabled` is false, e.g. while the plant talks or records,
 * so it can't wake itself by saying its own name.
 */
export function useWakeWord(name: string, enabled: boolean, onWake: () => void) {
  const Ctor = (window as unknown as Record<string, unknown>).SpeechRecognition ??
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  const supported = typeof Ctor === "function";
  const [active, setActive] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const onWakeRef = useRef(onWake);
  onWakeRef.current = onWake;

  useEffect(() => {
    if (!supported || !enabled || blocked || !name) return;
    const pattern = wakePattern(name);
    const recognition = new (Ctor as new () => Recognition)();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    let stopped = false;
    let fired = false;
    recognition.onresult = (event) => {
      let heard = "";
      for (let i = event.resultIndex; i < event.results.length; i++) heard += ` ${event.results[i][0].transcript}`;
      if (!fired && pattern.test(heard)) {
        fired = true;
        onWakeRef.current();
        recognition.abort(); // start fresh so the same words don't fire twice
      }
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") setBlocked(true);
    };
    recognition.onend = () => {
      setActive(false);
      if (!stopped) {
        fired = false;
        setTimeout(() => { if (!stopped) start(); }, 400);
      }
    };
    const start = () => {
      try {
        recognition.start();
        setActive(true);
      } catch {
        /* already running */
      }
    };
    start();
    return () => {
      stopped = true;
      recognition.onend = null;
      recognition.abort();
      setActive(false);
    };
  }, [supported, enabled, blocked, name, Ctor]);

  return { supported: supported && !blocked, active };
}
