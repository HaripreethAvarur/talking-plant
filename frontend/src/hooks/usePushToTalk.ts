import { useCallback, useEffect, useRef, useState } from "react";
import type { ChildUtterance } from "../contracts";

export type TalkStatus = "idle" | "listening" | "thinking" | "error";

const MIN_CLIP_MS = 400; // ignore accidental taps

/**
 * Push-to-talk for Task 3: hold the button (or the space bar) to record from
 * the laptop microphone; on release the clip goes to /api/stt and the
 * transcript is handed to onText.
 */
export function usePushToTalk(onText: (text: string, source: ChildUtterance["source"]) => void) {
  const [status, setStatus] = useState<TalkStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const send = async (blob: Blob) => {
    setStatus("thinking");
    try {
      const res = await fetch("/api/stt", {
        method: "POST",
        headers: { "content-type": blob.type || "audio/webm" },
        body: blob,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
      const utterance = (await res.json()) as ChildUtterance;
      onTextRef.current(utterance.text, "stt");
      setStatus("idle");
      setError(null);
    } catch (e) {
      console.warn("Speech-to-text failed:", e);
      setStatus("error");
      setError("I couldn't hear that. Tap a question below!");
    }
  };

  const start = useCallback(async () => {
    if (recorderRef.current?.state === "recording") return;
    try {
      streamRef.current ??= await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setStatus("error");
      setError("No microphone. Tap a question below!");
      return;
    }
    const recorder = new MediaRecorder(streamRef.current);
    chunksRef.current = [];
    recorder.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
    recorder.onstop = () => {
      if (performance.now() - startedAtRef.current < MIN_CLIP_MS) return setStatus("idle");
      void send(new Blob(chunksRef.current, { type: recorder.mimeType }));
    };
    recorderRef.current = recorder;
    startedAtRef.current = performance.now();
    recorder.start();
    setStatus("listening");
    setError(null);
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  // Space bar works like the button, unless someone is typing in a field.
  useEffect(() => {
    const typing = (e: KeyboardEvent) => (e.target as HTMLElement)?.tagName === "INPUT";
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || typing(e)) return;
      e.preventDefault();
      void start();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || typing(e)) return;
      e.preventDefault();
      stop();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [start, stop]);

  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  return { status, error, start, stop };
}
