import { useCallback, useEffect, useRef, useState } from "react";
import { viewerToken } from "../api";
import type { ChildUtterance } from "../contracts";

export type TalkStatus = "idle" | "listening" | "thinking" | "error";
const MIN_CLIP_MS = 400;
const SILENCE_MS = 1200; // after the child has spoken, this much quiet ends the recording
const SPEECH_LEVEL = 0.04; // RMS loudness that counts as talking (0..1)
const SPEECH_MS = 300; // this much loud audio counts as the child having started to talk
const GRACE_MS = 700; // ignore the first moment of a recording (the greeting's echo, a click)
export const LISTEN_MS = 8000; // a tap records this long unless tapped again

/** Tap-to-talk recording, plus the bounded window opened by the touch sensor. */
export function usePushToTalk(onText: (text: string, source: ChildUtterance["source"]) => void) {
  const [status, setStatus] = useState<TalkStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const busy = useRef(false);
  const armed = useRef(false);
  const generation = useRef(0);
  const pendingRequest = useRef<AbortController | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const stopListening = useRef<(() => void) | null>(null); // ends the silence detector

  const release = useCallback(() => {
    stopListening.current?.();
    stopListening.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    clearTimeout(timer.current);
  }, []);

  // Called on the first tap of the page. Permission is explicit; no recording yet.
  const prepare = useCallback(async () => {
    try {
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true });
      permission.getTracks().forEach((track) => track.stop());
      armed.current = true;
      setError(null);
      return true;
    } catch {
      setError("Allow microphone access to talk, or tap a question below.");
      setStatus("error");
      return false;
    }
  }, []);

  const stop = useCallback(() => {
    clearTimeout(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
    else if (!pendingRequest.current) {
      generation.current += 1; // A released button must cancel pending microphone acquisition.
      busy.current = false;
      release();
      setStatus("idle");
    }
  }, [release]);

  const cancel = useCallback(() => {
    generation.current += 1;
    pendingRequest.current?.abort();
    pendingRequest.current = null;
    if (recorder.current) {
      recorder.current.onstop = null;
      if (recorder.current.state === "recording") recorder.current.stop();
    }
    recorder.current = null;
    busy.current = false;
    release();
    setStatus("idle");
  }, [release]);

  const start = useCallback(async (durationMs = 15000) => {
    if (busy.current) return false;
    busy.current = true;
    const current = ++generation.current;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true } });
      if (current !== generation.current) {
        acquired.getTracks().forEach((track) => track.stop());
        return false;
      }
      armed.current = true;
      stream.current = acquired;
      const recording = new MediaRecorder(acquired);
      const chunks: Blob[] = [];
      const startedAt = performance.now();
      recording.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recording.onstop = async () => {
        release();
        recorder.current = null;
        if (current !== generation.current) return;
        if (performance.now() - startedAt < MIN_CLIP_MS) {
          busy.current = false;
          setStatus("idle");
          return;
        }
        setStatus("thinking");
        const controller = new AbortController();
        pendingRequest.current = controller;
        const deadline = setTimeout(() => controller.abort(), 15000);
        try {
          const token = viewerToken();
          const response = await fetch("/api/stt", {
            method: "POST",
            headers: { "content-type": recording.mimeType || "audio/webm", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            body: new Blob(chunks, { type: recording.mimeType }),
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("Speech recognition unavailable");
          const utterance = await response.json() as ChildUtterance;
          if (current === generation.current) {
            onTextRef.current(utterance.text, "stt");
            setStatus("idle");
          }
        } catch {
          if (current === generation.current) {
            setStatus("error");
            setError("I couldn't hear that. Tap a question below!");
          }
        } finally {
          clearTimeout(deadline);
          if (current === generation.current) {
            pendingRequest.current = null;
            busy.current = false;
          }
        }
      };
      recording.onerror = () => {
        cancel();
        setStatus("error");
        setError("Microphone recording failed. Try a question below.");
      };
      recorder.current = recording;
      recording.start();
      timer.current = setTimeout(stop, Math.min(15000, Math.max(1000, durationMs)));
      stopListening.current = whenQuiet(acquired, stop);
      setStatus("listening");
      setError(null);
      return true;
    } catch {
      if (current === generation.current) {
        release();
        busy.current = false;
        setStatus("error");
        setError("No microphone access. Tap the talk button to allow it, or use a question below.");
      }
      return false;
    }
  }, [cancel, release, stop]);

  // The touch sensor opens the mic. If permission was already granted (Chrome
  // remembers it), this just works; start() shows an error only if the browser refuses.
  const startFor = useCallback((durationMs: number) => start(durationMs), [start]);

  useEffect(() => {
    const typing = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      return ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName) || target?.isContentEditable;
    };
    // Space works like the big button: tap to start, tap again to stop.
    const down = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat || typing(event)) return;
      event.preventDefault();
      if (recorder.current?.state === "recording") stop();
      else void start(LISTEN_MS);
    };
    const hide = () => { if (document.hidden) cancel(); };
    window.addEventListener("keydown", down);
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.removeEventListener("keydown", down);
      document.removeEventListener("visibilitychange", hide);
      cancel();
    };
  }, [start, stop, cancel]);

  return { status, error, prepare, start, startFor, stop, cancel, isBusy: () => busy.current };
}

/**
 * Calls onQuiet once the child has really spoken (SPEECH_MS of loud audio, after a short
 * grace period that skips the greeting's echo) and then gone quiet for SILENCE_MS. Never
 * throws: if audio analysis isn't available, recording just runs to its normal limit.
 */
function whenQuiet(stream: MediaStream, onQuiet: () => void): () => void {
  try {
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Context) return () => {};
    const context = new Context();
    void context.resume().catch(() => undefined);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const startedAt = performance.now();
    let loudFor = 0;
    let spoke = false;
    let quietSince = 0;
    let last = startedAt;
    const timer = setInterval(() => {
      const now = performance.now();
      const step = now - last;
      last = now;
      if (now - startedAt < GRACE_MS) return;
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const value of samples) sum += value * value;
      const loud = Math.sqrt(sum / samples.length) > SPEECH_LEVEL;
      if (loud) {
        loudFor += step;
        if (loudFor >= SPEECH_MS) spoke = true;
        quietSince = 0;
      } else {
        loudFor = 0;
        if (spoke) {
          quietSince ||= now;
          if (now - quietSince >= SILENCE_MS) {
            clearInterval(timer);
            onQuiet();
          }
        }
      }
    }, 50);
    return () => {
      clearInterval(timer);
      void context.close().catch(() => undefined);
    };
  } catch {
    return () => {};
  }
}
