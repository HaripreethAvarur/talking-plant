import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { ChildUtterance, Face, Health, ListenRequest, PlantRegistration, SpeechAudio } from "./contracts";
import { ChatFeed, type ChatMessage } from "./components/ChatFeed";
import { DemoPanel } from "./components/DemoPanel";
import { LeaderboardPage } from "./components/LeaderboardPage";
import { PlantCharacter } from "./components/PlantCharacter";
import { Scene } from "./components/Scene";
import { SignUp } from "./components/SignUp";
import { StatCards } from "./components/StatCards";
import { TalkDock } from "./components/TalkDock";
import { usePlantSocket } from "./hooks/usePlantSocket";
import { usePlantVoice } from "./hooks/usePlantVoice";
import { LISTEN_MS, usePushToTalk } from "./hooks/usePushToTalk";

const OFFLINE_HEALTH = ["missing", "disconnected", "stale"];
const MAX_MESSAGES = 30;

const FALLBACK_HEALTH: Health = {
  stt: false,
  tts: false,
  llm: false,
  plant: { name: "Sprout", species: "plant" },
  quick_questions: ["Are you okay?", "What do you need?", "Do you like the sun?", "What's your name?"],
};

const CAPTIONS: Record<Face, string> = {
  happy: "Feeling great!",
  grateful: "Thank you!!",
  thirsty: "So thirsty…",
  soggy: "Too much water!",
  too_dark: "It's too dark!",
  sleepy: "Sleeping… zzz",
  unwell: "Not feeling well",
  offline: "Can't feel my roots",
};

type Tab = "plant" | "leaderboard";
const tabFromHash = (): Tab => (location.hash === "#leaderboard" ? "leaderboard" : "plant");

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [waiting, setWaiting] = useState(false);
  const [showDemo, setShowDemo] = useState(false);
  const [editing, setEditing] = useState<PlantRegistration | null>(null);
  const nextId = useRef(1);

  const say = useCallback((from: ChatMessage["from"], text: string) => {
    setMessages((list) => [...list, { id: nextId.current++, from, text }].slice(-MAX_MESSAGES));
  }, []);

  const voice = usePlantVoice();
  const talkRef = useRef<ReturnType<typeof usePushToTalk> | null>(null);
  const onAudio = (audio: SpeechAudio) => { if (!talkRef.current?.isBusy()) void voice.play(audio); };
  const speakingRef = useRef(false);
  speakingRef.current = voice.speaking;
  /** Resolves once the plant has finished talking (e.g. its greeting), so it isn't recorded. */
  const afterSpeech = async () => {
    const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
    for (let t = 0; t < 1200 && !speakingRef.current; t += 100) await wait(100); // greeting may still be loading
    for (let t = 0; t < 10000 && speakingRef.current; t += 100) await wait(100);
    await wait(250);
  };
  const onListen = (request: ListenRequest) => {
    if (document.hidden || !voice.unlocked || talkRef.current?.isBusy()) return;
    // The backend sends the greeting first: record after it, so the child answers what they heard.
    void afterSpeech().then(() => talkRef.current?.startFor(request.duration_ms));
  };
  const { state, connected, sendUtterance } = usePlantSocket(onAudio, onListen);

  const ask = useCallback(
    (text: string, source: ChildUtterance["source"]) => {
      say("kid", text);
      setWaiting(true);
      sendUtterance(text, source);
    },
    [say, sendUtterance],
  );
  const talk = usePushToTalk(ask);
  talkRef.current = talk;

  useEffect(() => { if (!connected) talk.cancel(); }, [connected, talk.cancel]);

  const loadHealth = useCallback(() => {
    api<Health>("/api/health").then(setHealth).catch(() => setHealth(FALLBACK_HEALTH));
  }, []);
  useEffect(loadHealth, [connected, loadHealth]);

  // Every line the plant says goes into the chat.
  useEffect(() => {
    if (state?.message) {
      say("plant", state.message);
      setWaiting(false);
    }
  }, [state, say]);
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => setWaiting(false), 15000);
    return () => clearTimeout(timer);
  }, [waiting]);

  // Tabs live in the URL hash so the browser's back button works.
  useEffect(() => {
    const sync = () => setTab(tabFromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  // Browsers keep sound and the microphone off until the first tap or key press anywhere.
  useEffect(() => {
    if (voice.unlocked) return;
    const wake = () => { void voice.unlock().then(() => talk.prepare()); };
    window.addEventListener("pointerdown", wake, { once: true });
    window.addEventListener("keydown", wake, { once: true });
    return () => {
      window.removeEventListener("pointerdown", wake);
      window.removeEventListener("keydown", wake);
    };
  }, [voice.unlocked, voice.unlock, talk.prepare]);

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
  const name = info.plant.name;
  const offline = !state || OFFLINE_HEALTH.includes(state.sensor_health ?? "missing");
  const face: Face = offline ? "offline" : state.mood;
  const listening = talk.status === "listening";

  const onMic = () => {
    if (listening) return talk.stop();
    voice.stop();
    void voice.unlock().then(() => talk.start(LISTEN_MS));
  };

  if (health && !health.registered) {
    return (
      <div className="app">
        <Scene face="happy" />
        <SignUp onDone={loadHealth} />
      </div>
    );
  }

  if (editing) {
    return (
      <div className="app">
        <Scene face="happy" />
        <SignUp initial={editing} onCancel={() => setEditing(null)} onDone={() => { setEditing(null); void loadHealth(); }} />
      </div>
    );
  }

  return (
    <div className={`app face-${face}`}>
      <Scene face={tab === "leaderboard" ? "happy" : face} night={state?.is_night} weatherCode={state?.weather_code} lightPct={state?.light_pct} />

      <header className="topbar">
        <div className="brand">
          <span className="brand-badge" aria-hidden>🌱</span>
          <h1>{name}</h1>
          <button className="edit-plant" title="Change my details" aria-label="Change my details"
            onClick={() => void api<PlantRegistration>("/api/plant").then(setEditing).catch(() => undefined)}>
            ✏️
          </button>
        </div>
        <nav className="tabs" aria-label="Pages">
          <a href="#plant" className={tab === "plant" ? "tab tab-on" : "tab"} aria-current={tab === "plant" ? "page" : undefined}>
            🪴 My Plant
          </a>
          <a href="#leaderboard" className={tab === "leaderboard" ? "tab tab-on" : "tab"} aria-current={tab === "leaderboard" ? "page" : undefined}>
            🏆 Leaderboard
          </a>
        </nav>
        <div className="status">
          <span className={`dot ${connected ? "dot-on" : "dot-off"}`} title={connected ? "Connected" : "Reconnecting…"} />
        </div>
      </header>

      {!voice.unlocked && (
        <button className="sound-banner" onClick={() => void voice.unlock().then(() => talk.prepare())}>
          🔈 Tap anywhere to turn on my voice!
        </button>
      )}

      {tab === "leaderboard" ? (
        <LeaderboardPage />
      ) : (
        <>
          <main className="home">
            <section className="stage">
              {listening && <span className="stage-badge badge-listen">👂 I'm listening!</span>}
              {talk.status === "thinking" && <span className="stage-badge badge-think">💭 Thinking…</span>}
              <div className="stage-plant">
                <PlantCharacter face={face} speaking={voice.speaking} level={voice.level} listening={listening} />
              </div>
              <span className={`caption caption-${face}`}>{CAPTIONS[face]}</span>
            </section>
            <div className="side">
              <ChatFeed
                plantName={name}
                messages={messages}
                    thinking={waiting || talk.status === "thinking"}
                hint={`Say hi to ${name}! Pat my leaf, tap the microphone, or pick a question below.`}
              />
              <StatCards state={state} face={face} dry={info.thresholds?.dry ?? 30} soggy={info.thresholds?.soggy ?? 90} />
            </div>
          </main>
          <TalkDock
            status={talk.status}
            error={talk.error}
            quickQuestions={info.quick_questions}
            onMic={onMic}
            onQuestion={(q) => ask(q, "button")}
          />
        </>
      )}

      {showDemo && <DemoPanel demoMode={!!info.demo_mode} onClose={() => setShowDemo(false)} />}
    </div>
  );
}
