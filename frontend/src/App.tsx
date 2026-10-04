import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { ChildUtterance, Face, Health, ListenRequest, SpeechAudio } from "./contracts";
import { DemoPanel } from "./components/DemoPanel";
import { Gauge } from "./components/Gauge";
import { LeaderboardPanel } from "./components/LeaderboardPanel";
import { PlantCharacter } from "./components/PlantCharacter";
import { SignUp } from "./components/SignUp";
import { TalkPanel } from "./components/TalkPanel";
import { usePlantSocket } from "./hooks/usePlantSocket";
import { usePlantVoice } from "./hooks/usePlantVoice";
import { usePushToTalk } from "./hooks/usePushToTalk";

const LIGHT_LOW = 20; // display only; the mood engine uses the profile's raw-light thresholds
const OFFLINE_HEALTH = ["missing", "disconnected", "stale"];

const FALLBACK_HEALTH: Health = {
  stt: false,
  tts: false,
  llm: false,
  plant: { name: "Sprout", species: "plant" },
  quick_questions: ["Are you okay?", "What do you need?", "Do you like the sun?", "What's your name?"],
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [plantLine, setPlantLine] = useState<string | null>(null);
  const [childLine, setChildLine] = useState<string | null>(null);
  const [showBoard, setShowBoard] = useState(false);
  const [showDemo, setShowDemo] = useState(false);

  const voice = usePlantVoice();
  const talkRef = useRef<ReturnType<typeof usePushToTalk> | null>(null);
  const onAudio = (audio: SpeechAudio) => { if (!talkRef.current?.isBusy()) void voice.play(audio); };
  const onListen = (request: ListenRequest) => {
    if (document.hidden || !voice.unlocked || talkRef.current?.isBusy()) return;
    voice.stop();
    void talkRef.current?.startFor(request.duration_ms);
  };
  const { state, connected, sendUtterance } = usePlantSocket(onAudio, onListen);

  const ask = useCallback(
    (text: string, source: ChildUtterance["source"]) => {
      setChildLine(text);
      sendUtterance(text, source);
    },
    [sendUtterance],
  );
  const talk = usePushToTalk(ask);
  talkRef.current = talk;

  useEffect(() => { if (!connected) talk.cancel(); }, [connected, talk.cancel]);

  const loadHealth = useCallback(() => {
    api<Health>("/api/health").then(setHealth).catch(() => setHealth(FALLBACK_HEALTH));
  }, []);
  useEffect(loadHealth, [connected, loadHealth]);

  useEffect(() => {
    if (state?.message) setPlantLine(state.message);
  }, [state]);

  // Shift+D toggles the hidden demo controls.
  useEffect(() => {
    const toggle = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key.toLowerCase() === "d" && (e.target as HTMLElement)?.tagName !== "INPUT") {
        setShowDemo((shown) => !shown);
      }
    };
    window.addEventListener("keydown", toggle);
    return () => window.removeEventListener("keydown", toggle);
  }, []);

  const info = health ?? FALLBACK_HEALTH;
  const offline = !state || OFFLINE_HEALTH.includes(state.sensor_health ?? "missing");
  // An old line ("Thank you!") shouldn't linger once the sensors stop; later replies still show.
  useEffect(() => { if (offline) setPlantLine(null); }, [offline]);
  const face: Face = offline ? "offline" : state.mood;
  const needsSignUp = health?.registered === false;

  return (
    <main className={`app mood-${face}`}>
      {needsSignUp && <SignUp onDone={loadHealth} />}
      {!needsSignUp && !voice.unlocked && (
        <button className="wake-overlay" onClick={async () => { await voice.unlock(); await talk.prepare(); }}>
          <span className="wake-emoji" aria-hidden>🪴</span>
          Tap to wake up {info.plant.name} and enable the microphone!
        </button>
      )}
      {showBoard && <LeaderboardPanel onClose={() => setShowBoard(false)} />}
      {showDemo && <DemoPanel demoMode={!!info.demo_mode} onClose={() => setShowDemo(false)} />}

      <header className="top-bar">
        <h1>{info.plant.name}</h1>
        {info.database && (
          <button className="board-button" onClick={() => setShowBoard(true)} aria-label="Leaderboard">🏆</button>
        )}
        <span className={`conn ${connected ? "conn-on" : "conn-off"}`} title={connected ? "Connected to the plant" : "Reconnecting…"} />
      </header>

      <section className="stage">
        <div className="bubbles">
          {offline && !plantLine && (
            <div className="bubble bubble-plant">I can't feel my roots right now. Is my sensor plugged in?</div>
          )}
          {plantLine && (
            <div key={plantLine} className={`bubble bubble-plant ${voice.speaking ? "bubble-speaking" : ""}`}>
              {plantLine}
            </div>
          )}
          {childLine && <div className="bubble bubble-child">You asked: “{childLine}”</div>}
        </div>
        <PlantCharacter face={face} speaking={voice.speaking} level={voice.level} />
      </section>

      <section className="gauges">
        <Gauge label="Water" icon="💧" value={state?.moisture_pct ?? null}
          low={info.thresholds?.dry ?? 30} high={info.thresholds?.soggy} color="var(--water)" />
        <Gauge label="Sunlight" icon="☀️" value={state?.light_pct ?? null} low={LIGHT_LOW} color="var(--sun)" />
      </section>

      <TalkPanel
        status={talk.status}
        error={talk.error}
        sttAvailable={info.stt}
        quickQuestions={info.quick_questions}
        onPressStart={() => { voice.stop(); void talk.start(); }}
        onPressEnd={talk.stop}
        onQuestion={(q) => ask(q, "button")}
      />
    </main>
  );
}
