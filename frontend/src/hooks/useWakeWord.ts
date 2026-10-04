import { useEffect, useRef, useState } from "react";

const GREETINGS = new Set(["hey", "hi", "hello", "hiya", "yo", "howdy", "okay", "ok", "high", "hay", "hei"]);

function words(text: string): string[] {
  return text.toLowerCase().replace(/[^a-z\s]/g, " ").split(/\s+/).filter(Boolean);
}

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let previous = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const current = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = current;
    }
  }
  return row[b.length];
}

/** Speech recognition often mishears names ("Jack Sparrow", "cap's barrow"): short name
 * words must match exactly, longer ones may be off by two letters. */
function soundsLike(heard: string, nameWord: string): boolean {
  if (heard === nameWord) return true;
  return nameWord.length >= 5 && heard.length >= 4 && distance(heard, nameWord) <= 2;
}

/** True for "Hi <name>" (a greeting, then a name word within three words) or the full name alone. */
export function heardWake(heard: string, name: string): boolean {
  const said = words(heard);
  const nameWords = words(name).filter((w) => w.length >= 3);
  if (!nameWords.length) return false;
  for (let i = 0; i < said.length; i++) {
    if (GREETINGS.has(said[i]) && said.slice(i + 1, i + 4).some((w) => nameWords.some((n) => soundsLike(w, n)))) {
      return true;
    }
    if (nameWords.length > 1 && nameWords.every((n, k) => said[i + k] !== undefined && soundsLike(said[i + k], n))) {
      return true;
    }
  }
  return false;
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
    const recognition = new (Ctor as new () => Recognition)();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    let stopped = false;
    let fired = false;
    recognition.onresult = (event) => {
      let heard = "";
      for (let i = event.resultIndex; i < event.results.length; i++) heard += ` ${event.results[i][0].transcript}`;
      if (!fired && heardWake(heard, name)) {
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
