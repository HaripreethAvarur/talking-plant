import type { Face, Mood, PlantState } from "../contracts";

interface Props {
  state: PlantState | null;
  face: Face;
  dry: number;
  soggy: number;
}

type Tone = "good" | "warn" | "bad" | "calm" | "none";

function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

function Meter({ value, color, marks = [] }: { value: number | null; color: string; marks?: number[] }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="meter" role="meter" aria-label="Sensor reading" aria-valuetext={value == null ? "Waiting for sensor" : undefined} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value == null ? undefined : Math.round(pct)}>
      <div className="meter-fill" style={{ width: `${pct}%`, background: color }} />
      {marks.map((m) => <span key={m} className="meter-mark" style={{ left: `${m}%` }} />)}
    </div>
  );
}

function ago(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "";
  const minutes = Math.max(0, Math.round((Date.now() / 1000 - epochSeconds) / 60));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} h ago`;
}

function air(aqi: number | null | undefined): [Tone, string] {
  if (aqi == null) return ["none", "Checking…"];
  if (aqi <= 50) return ["good", "Fresh air!"];
  if (aqi <= 100) return ["warn", "Okay air"];
  if (aqi <= 150) return ["bad", "Not great"];
  return ["bad", "Yucky air"];
}

const CHECKUP: Record<Mood, [Tone, string]> = {
  happy: ["good", "Looking great!"],
  grateful: ["good", "Looking great!"],
  thirsty: ["warn", "Needs a drink"],
  soggy: ["warn", "Too wet"],
  too_dark: ["warn", "Needs light"],
  sleepy: ["calm", "Resting"],
  unwell: ["bad", "Needs care"],
};

/** Four big, friendly gauges: water, sunshine, air and how the plant looks on camera. */
export function StatCards({ state, face, dry, soggy }: Props) {
  const water = state?.moisture_pct ?? null;
  const sun = state?.light_pct ?? null;
  const [waterTone, waterText]: [Tone, string] =
    water == null ? ["none", "Can't tell yet"] : water < dry ? ["bad", "Thirsty!"] : water > soggy ? ["warn", "Too wet!"] : ["good", "Just right"];
  const [sunTone, sunText]: [Tone, string] =
    sun == null ? ["none", "Can't tell yet"] : face === "sleepy" ? ["calm", "Night time"] : face === "too_dark" ? ["bad", "Too dark!"] : ["good", "Sunny!"];
  const [airTone, airText] = air(state?.air_aqi);
  const [lookTone, lookText] = state?.checkup_mood ? CHECKUP[state.checkup_mood] : (["none", "Soon!"] as [Tone, string]);

  return (
    <section className="stats">
      <article className="stat card stat-water">
        <header><span className="title-icon bg-blue">💧</span> Water</header>
        <strong className="stat-value">{water == null ? "–" : `${Math.round(water)}%`}</strong>
        <Meter value={water} color="linear-gradient(90deg,#3ab0ff,#5bd0ff)" marks={[dry, soggy]} />
        <Chip tone={waterTone}>{waterText}</Chip>
      </article>

      <article className="stat card stat-sun">
        <header><span className="title-icon bg-yellow">☀️</span> Sunshine</header>
        <strong className="stat-value">{sun == null ? "–" : `${Math.round(sun)}%`}</strong>
        <Meter value={sun} color="linear-gradient(90deg,#ffb020,#ffd23f)" />
        <Chip tone={sunTone}>{sunText}</Chip>
      </article>

      <article className="stat card stat-air">
        <header><span className="title-icon bg-teal">🌬️</span> Air</header>
        <strong className="stat-value">
          {state?.air_aqi == null ? "–" : Math.round(state.air_aqi)}
          <small> AQI</small>
        </strong>
        <p className="aqi-explanation">Outdoor air · lower AQI is better</p>
        <Chip tone={airTone}>{airText}</Chip>
      </article>

      <article className="stat card stat-look">
        <header><span className="title-icon bg-purple">📸</span> How I look</header>
        <p className="look-text" title={state?.looks ?? undefined}>
          {state?.looks ?? "I'll take a selfie soon!"}
        </p>
        <div className="look-foot">
          <Chip tone={lookTone}>{lookText}</Chip>
          {state?.looks_at && <span className="look-time">{ago(state.looks_at)}</span>}
        </div>
      </article>
    </section>
  );
}
