import { useCallback, useEffect, useState } from "react";
import type { ChildUtterance, Health } from "./contracts";
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
  const { state, connected, sendUtterance } = usePlantSocket(voice.play);

  const ask = useCallback(
    (text: string, source: ChildUtterance["source"]) => {
      setChildLine(text);
      sendUtterance(text, source);
    },
    [sendUtterance],
  );
  const talk = usePushToTalk(ask);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
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
        <button className="wake-overlay" onClick={voice.unlock}>
          <span className="wake-emoji" aria-hidden>🪴</span>
          Tap to wake up {health.plant.name}!
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
        onPressStart={talk.start}
        onPressEnd={talk.stop}
        onQuestion={(q) => ask(q, "button")}
      />
    </main>
  );
}
