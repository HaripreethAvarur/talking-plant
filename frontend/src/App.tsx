import { useCallback, useEffect, useRef, useState } from "react";
import { readAudience, saveAudience, type Audience } from "./audience";
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
  const [showConversation, setShowConversation] = useState(false);
  const [audience, setAudience] = useState<Audience>(readAudience);
  const changeAudience = (value: Audience) => { setAudience(value); saveAudience(value); };
  const lastMessage = useRef<string | null>(null);

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
      if (!sendUtterance(text, source)) return;
      say("kid", text);
      setWaiting(true);
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
    if (state?.message && `${state.ts}:${state.message}` !== lastMessage.current) {
      lastMessage.current = `${state.ts}:${state.message}`;
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
  const offline = !connected || !state || OFFLINE_HEALTH.includes(state.sensor_health ?? "missing");
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
        <Scene face="happy" timezone={health?.plant.timezone} />
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
      <Scene face={tab === "leaderboard" ? "happy" : face} timezone={info.plant.timezone} night={state?.is_night} lightPct={state?.light_pct} />

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
            My garden
          </a>
          <a href="#leaderboard" className={tab === "leaderboard" ? "tab tab-on" : "tab"} aria-current={tab === "leaderboard" ? "page" : undefined}>
            Garden club
          </a>
        </nav>
        <div className="status">
          <span className="connection-label">{connected ? "Live" : "Connecting"}</span>
          <span className={`dot ${connected ? "dot-on" : "dot-off"}`} title={connected ? "Connected" : "Reconnecting…"} />
        </div>
      </header>

      {!voice.unlocked && tab === "plant" && (
        <button className="sound-banner" onClick={() => void voice.unlock().then(() => talk.prepare())}>
          Turn on plant voice
        </button>
      )}

      {tab === "leaderboard" ? (
        <LeaderboardPage />
      ) : (
        <>
          <main className="home">
            <section className="stage" aria-label={`${name}'s garden`}>
              <div className="garden-intro"><span className="eyebrow">{info.username ? `${info.username}’s garden` : "YOUR LITTLE CORNER OF NATURE"}</span><h2>{audience === "5-7" ? "Hello, little grower!" : audience === "12-15" ? "Your plant. Your world." : "Let’s grow something good."}</h2><p>A living friend. Something new to discover every day.</p></div>
              <div className="plant-speech" role="status">
                <span className="eyebrow">{name}</span>
                <p>{listening ? "I'm listening. What's on your mind?" : waiting || talk.status === "thinking" ? "Let me think about that…" : [...messages].reverse().find(m => m.from === "plant")?.text ?? (offline ? "My sensors are taking a little break. I'll be back soon." : `Hi! I'm ${name}. Come say hello.`)}</p>
              </div>
              <div className="stage-plant">
                <PlantCharacter face={face} speaking={voice.speaking} level={voice.level} listening={listening} />
              </div>
              <span className={`caption caption-${face}`}>{CAPTIONS[face]}</span>
            </section>
          <TalkDock
            status={talk.status}
            error={talk.error}
            plantName={name}
            disabled={!connected || waiting}
            quickQuestions={info.quick_questions}
            onMic={onMic}
            onQuestion={(q) => ask(q, "button")}
          />
            <section className="garden-tools" aria-label="Plant care">
              <div className="readings-header"><div><span className="eyebrow">MY WORLD RIGHT NOW</span><h3>How I’m doing</h3></div></div>
              <StatCards state={state} sensorOffline={offline} face={face} audience={audience} dry={info.thresholds?.dry ?? 30} soggy={info.thresholds?.soggy ?? 90} />
              <div className="panel-tabs"><details className="reading-settings"><summary>Reading style</summary><label>Show information as<select aria-label="Reading style" value={audience} onChange={e => changeAudience(e.target.value as Audience)}><option value="5-7">Simple</option><option value="8-11">Curious</option><option value="12-15">More science</option></select></label></details><button aria-expanded={showConversation} aria-controls="garden-conversation" onClick={() => setShowConversation(!showConversation)}>{showConversation ? "Hide conversation" : "Our conversation"}</button></div>
              <div id="garden-conversation">{showConversation && <ChatFeed messages={messages} plantName={name} thinking={waiting || talk.status === "thinking"} hint={`Your conversation with ${name} will appear here.`} />}</div>
            </section>
          </main>

        </>
      )}

      <footer className="garden-footer">Grow curious. <span>v0.0.2</span></footer>
      {showDemo && <DemoPanel demoMode={!!info.demo_mode} onClose={() => setShowDemo(false)} />}
    </div>
  );
}
