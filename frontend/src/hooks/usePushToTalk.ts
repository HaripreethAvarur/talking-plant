import { useCallback, useEffect, useRef, useState } from "react";
import type { ChildUtterance } from "../contracts";

export type TalkStatus = "idle" | "listening" | "thinking" | "error";
const MIN_CLIP_MS = 400;

/** Manual push-to-talk plus a bounded, previously authorized hardware-touch window. */
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

  const release = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    clearTimeout(timer.current);
  }, []);

  // Called from the browser's wake button. Permission is explicit; no recording yet.
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
          const token = sessionStorage.getItem("plantViewerToken");
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

  const startFor = useCallback(async (durationMs: number) => {
    if (!armed.current) {
      setError("Tap the talk button once to allow the microphone before using the touch sensor.");
      setStatus("error");
      return false;
    }
    return start(durationMs);
  }, [start]);

  useEffect(() => {
    const typing = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      return ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName) || target?.isContentEditable;
    };
    const down = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat || typing(event)) return;
      event.preventDefault();
      void start();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || typing(event)) return;
      event.preventDefault();
      stop();
    };
    const hide = () => { if (document.hidden) cancel(); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      document.removeEventListener("visibilitychange", hide);
      cancel();
    };
  }, [start, stop, cancel]);

  return { status, error, prepare, start, startFor, stop, cancel, isBusy: () => busy.current };
}
