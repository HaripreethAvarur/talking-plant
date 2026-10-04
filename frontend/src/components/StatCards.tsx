import type { Audience } from "../audience";
import type { Face, PlantState } from "../contracts";

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

/** An emoji for the WMO weather code (night swaps the sun for a moon). */
function weatherIcon(code: number | null | undefined, night: boolean): string {
  if (code == null) return "🌡️";
  if (code === 0 || code === 1) return night ? "🌙" : "☀️";
  if (code === 2) return night ? "☁️" : "⛅";
  if (code === 3 || code === 45 || code === 48) return "☁️";
  if (code >= 95) return "⛈️";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "❄️";
  return "🌧️";
}

function air(aqi: number | null | undefined): [Tone, string] {
  if (aqi == null) return ["none", "Checking…"];
  if (aqi <= 50) return ["good", "Fresh air!"];
  if (aqi <= 100) return ["warn", "Okay air"];
  if (aqi <= 150) return ["bad", "Not great"];
  return ["bad", "Yucky air"];
}

const LEAF_WORDS: Record<string, string> = { yellowing: "yellow", browning: "brown", wilting: "droopy" };
const LOOKS_WORRY = /\b(yellow|brown|spots?|droop|drooping|wilt|wilting|wilted|dry leaves|unhealthy)\b/i;

/** The look card is about the leaves only, so it can't contradict the water or sun cards. */
function leaves(state: PlantState | null): [Tone, string] {
  const issues = state?.leaf_issues;
  if (issues && issues.length) return ["bad", `Leaves look ${issues.map((i) => LEAF_WORDS[i] ?? i).join(" & ")}`];
  if (issues) return ["good", "Healthy leaves"];
  if (state?.looks) return LOOKS_WORRY.test(state.looks) ? ["warn", "Check my leaves"] : ["good", "Healthy leaves"];
  return ["none", "Soon!"];
}

/** Four big, friendly gauges: water, sunshine, the weather outside and how the plant looks on camera. */
export function StatCards({ state, face, dry, soggy, audience, sensorOffline }: Props) {
  const water = sensorOffline ? null : state?.moisture_pct ?? null;
  const sun = sensorOffline ? null : state?.light_pct ?? null;
  const [waterTone, waterText]: [Tone, string] =
    water == null ? ["none", "Can't tell yet"] : water < dry ? ["bad", "Thirsty!"] : water > soggy ? ["warn", "Too wet!"] : ["good", "Just right"];
  const [sunTone, sunText]: [Tone, string] =
    sun == null ? ["none", "Can't tell yet"]
      : state?.is_night || face === "sleepy" ? ["calm", "Night time"]
      : face === "too_dark" ? ["bad", "Too dark!"]
      : ["good", "Sunny!"];
  const [airTone, airText] = air(state?.air_aqi);
  const [lookTone, lookText] = leaves(state);

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
        <header><span className="title-icon bg-teal">{weatherIcon(state?.weather_code, !!state?.is_night)}</span> Outside</header>
        <strong className="stat-value">
          {state?.outdoor_temp_f == null ? "–" : `${Math.round(state.outdoor_temp_f)}°F`}
        </strong>
        <p className="outside-line">
          {state?.weather ?? "Checking the weather…"}
          {audience !== "5-7" && state?.outdoor_humidity != null && ` · ${Math.round(state.outdoor_humidity)}% humid`}
        </p>
        <Chip tone={airTone}>{audience === "5-7" || state?.air_aqi == null ? airText : `${airText} · AQI ${Math.round(state.air_aqi)}`}</Chip>
        {audience === "12-15" && <p className="aqi-explanation">Outdoor US AQI · lower is better; not an indoor sensor</p>}
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
