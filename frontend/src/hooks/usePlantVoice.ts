import { useCallback, useEffect, useRef, useState } from "react";
import type { SpeechAudio } from "../contracts";

/**
 * Plays the plant's lines through the speaker and reports a 0..1 loudness
 * level so the mouth can move with the audio.
 *
 * ElevenLabs clips are routed through a Web Audio analyser. When the backend
 * had no audio (no key, offline and not cached) the browser's own speech
 * synthesis says the line instead, and the mouth flaps on a timer.
 *
 * Browsers block sound until the user interacts with the page, so call
 * unlock() from a click before the first line.
 */
export function usePlantVoice() {
  const [speaking, setSpeaking] = useState(false);
  const [level, setLevel] = useState(0);
  const [unlocked, setUnlocked] = useState(false);

  const ctxRef = useRef<AudioContext | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number>();
  const modeRef = useRef<"audio" | "synth" | null>(null);

  const stopLoop = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = undefined;
  };

  const finish = useCallback(() => {
    stopLoop();
    modeRef.current = null;
    setSpeaking(false);
    setLevel(0);
  }, []);

  const startLoop = useCallback(() => {
    stopLoop();
    const buf = new Uint8Array(analyserRef.current?.fftSize ?? 1024);
    const tick = (t: number) => {
      if (modeRef.current === "audio" && analyserRef.current) {
        analyserRef.current.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
      } else if (modeRef.current === "synth") {
        setLevel(0.25 + 0.35 * Math.abs(Math.sin(t / 90)));
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const unlock = useCallback(async () => {
    if (!ctxRef.current) {
      const ctx = new AudioContext();
      const audio = new Audio();
      audio.crossOrigin = "anonymous";
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaElementSource(audio).connect(analyser);
      analyser.connect(ctx.destination);
      audio.onended = finish;
      audio.onerror = finish;
      ctxRef.current = ctx;
      audioRef.current = audio;
      analyserRef.current = analyser;
    }
    await ctxRef.current.resume();
    setUnlocked(true);
  }, [finish]);

  const speakWithBrowser = useCallback(
    (text: string) => {
      if (!("speechSynthesis" in window)) return finish();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1.0;
      u.pitch = 1.3;
      u.onend = finish;
      u.onerror = finish;
      modeRef.current = "synth";
      setSpeaking(true);
      startLoop();
      window.speechSynthesis.speak(u);
    },
    [finish, startLoop],
  );

  const play = useCallback(
    async (speech: SpeechAudio) => {
      // A new line always interrupts the old one.
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
      finish();

      const audio = audioRef.current;
      if (!speech.audio_url || !audio) return speakWithBrowser(speech.text);
      try {
        audio.src = speech.audio_url;
        modeRef.current = "audio";
        setSpeaking(true);
        startLoop();
        await audio.play();
      } catch {
        speakWithBrowser(speech.text);
      }
    },
    [finish, speakWithBrowser, startLoop],
  );

  useEffect(() => () => stopLoop(), []);

  return { play, unlock, unlocked, speaking, level };
}
