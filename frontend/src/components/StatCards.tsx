import type { Audience } from "../audience";
import type { Face, Mood, PlantState } from "../contracts";

interface Props {
  state: PlantState | null;
  audience: Audience;
  sensorOffline: boolean;
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
export function StatCards({ state, face, dry, soggy, audience, sensorOffline }: Props) {
  const water = sensorOffline ? null : state?.moisture_pct ?? null;
  const sun = sensorOffline ? null : state?.light_pct ?? null;
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
        <strong className="stat-value">{audience === "5-7" ? waterText : water == null ? "–" : `${Math.round(water)}%`}</strong>
        {audience !== "5-7" && <Meter value={water} color="linear-gradient(90deg,#3ab0ff,#5bd0ff)" marks={[dry, soggy]} />}
        {audience !== "5-7" && <p className="reading-detail">{audience === "12-15" ? `Soil moisture · care band ${dry}–${soggy}%` : "How wet my soil feels"}</p>}
        {audience !== "5-7" && <Chip tone={waterTone}>{waterText}</Chip>}
      </article>

      <article className="stat card stat-sun">
        <header><span className="title-icon bg-yellow">☀️</span> Sunshine</header>
        <strong className="stat-value">{audience === "5-7" ? sunText : sun == null ? "–" : `${Math.round(sun)}%`}</strong>
        {audience !== "5-7" && <Meter value={sun} color="linear-gradient(90deg,#ffb020,#ffd23f)" />}
        {audience !== "5-7" && <p className="reading-detail">{audience === "12-15" ? `Relative light level${state?.light_value == null ? "" : ` · ${Math.round(state.light_value)} ${state.light_unit ?? "raw"}`}` : "Light helps me grow"}</p>}
        {audience !== "5-7" && <Chip tone={sunTone}>{sunText}</Chip>}
      </article>

      <article className="stat card stat-air">
        <header><span className="title-icon bg-teal">🌬️</span> Air</header>
        <strong className="stat-value">
          {audience === "5-7" ? airText : state?.air_aqi == null ? "–" : Math.round(state.air_aqi)}
          {audience !== "5-7" && <small> AQI</small>}
        </strong>
        <p className="aqi-explanation">{audience === "5-7" ? "The air outside near my home" : audience === "8-11" ? "Outdoor air · smaller numbers mean cleaner air" : "Outdoor US AQI · lower is better; not an indoor sensor"}</p>
        {audience !== "5-7" && <Chip tone={airTone}>{airText}</Chip>}
      </article>

      <article className="stat card stat-look">
        <header><span className="title-icon bg-purple">📸</span> How I look</header>
        <p className="look-text" title={state?.looks ?? undefined}>
          {audience === "5-7" ? lookText : state?.looks ?? "I’ll take a selfie soon!"}
        </p>
        <div className="look-foot">
          <Chip tone={lookTone}>{lookText}</Chip>
          {state?.looks_at && <span className="look-time">{ago(state.looks_at)}</span>}
        </div>
      </article>
    </section>
  );
}
