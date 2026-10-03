import { useCallback, useEffect, useRef, useState } from "react";
import type { ChildUtterance, Health, ListenRequest, SpeechAudio } from "./contracts";
import { Gauge } from "./components/Gauge";
import { PlantCharacter } from "./components/PlantCharacter";
import { TalkPanel } from "./components/TalkPanel";
import { usePlantSocket } from "./hooks/usePlantSocket";
import { usePlantVoice } from "./hooks/usePlantVoice";
import { usePushToTalk } from "./hooks/usePushToTalk";

// Display thresholds for the gauges; the agent's own thresholds come from the plant profile (Task 6).
const MOISTURE_LOW = 30;
const LIGHT_LOW = 20;

const FALLBACK_HEALTH: Health = {
  stt: false,
  tts: false,
  llm: false,
  plant: { name: "Sprout", species: "plant" },
  quick_questions: ["Are you okay?", "What do you need?", "Do you like the sun?", "What's your name?"],
};

export default function App() {
  const [health, setHealth] = useState<Health>(FALLBACK_HEALTH);
  const [plantLine, setPlantLine] = useState<string | null>(null);
  const [childLine, setChildLine] = useState<string | null>(null);

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

  useEffect(() => {
    const token = sessionStorage.getItem("plantViewerToken");
    fetch("/api/health", { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => { if (!r.ok) throw new Error("Health unavailable"); return r.json(); })
      .then(setHealth)
      .catch(() => setHealth(FALLBACK_HEALTH));
  }, [connected]);

  useEffect(() => {
    if (state?.message) setPlantLine(state.message);
  }, [state]);

  const mood = state?.mood ?? "happy";

  return (
    <main className={`app mood-${mood}`}>
      {!voice.unlocked && (
        <button className="wake-overlay" onClick={async () => { await voice.unlock(); await talk.prepare(); }}>
          <span className="wake-emoji" aria-hidden>🪴</span>
          Tap to wake up {health.plant.name} and enable the microphone!
        </button>
      )}

      <header className="top-bar">
        <h1>{health.plant.name}</h1>
        <span className={`conn ${connected ? "conn-on" : "conn-off"}`} title={connected ? "Connected to the plant" : "Reconnecting…"} />
      </header>

      <section className="stage">
        <div className="bubbles">
          {plantLine && (
            <div key={plantLine} className={`bubble bubble-plant ${voice.speaking ? "bubble-speaking" : ""}`}>
              {plantLine}
            </div>
          )}
          {childLine && <div className="bubble bubble-child">You asked: “{childLine}”</div>}
        </div>
        <PlantCharacter mood={mood} speaking={voice.speaking} level={voice.level} />
      </section>

      <section className="gauges">
        <Gauge label="Water" icon="💧" value={state?.moisture_pct ?? null} low={MOISTURE_LOW} color="var(--water)" />
        <Gauge label="Sunlight" icon="☀️" value={state?.light_pct ?? null} low={LIGHT_LOW} color="var(--sun)" />
      </section>

      <TalkPanel
        status={talk.status}
        error={talk.error}
        sttAvailable={health.stt}
        quickQuestions={health.quick_questions}
        onPressStart={() => { voice.stop(); void talk.start(); }}
        onPressEnd={talk.stop}
        onQuestion={(q) => ask(q, "button")}
      />
    </main>
  );
}
