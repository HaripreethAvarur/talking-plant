import type { Face, PlantState } from "../contracts";

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
    <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
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
export function StatCards({ state, face, dry, soggy }: Props) {
  const water = state?.moisture_pct ?? null;
  const sun = state?.light_pct ?? null;
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
        <header><span className="title-icon bg-teal">{weatherIcon(state?.weather_code, !!state?.is_night)}</span> Outside</header>
        <strong className="stat-value">
          {state?.outdoor_temp_f == null ? "–" : `${Math.round(state.outdoor_temp_f)}°F`}
        </strong>
        <p className="outside-line">
          {state?.weather ?? "Checking the weather…"}
          {state?.outdoor_humidity != null && ` · ${Math.round(state.outdoor_humidity)}% humid`}
        </p>
        <Chip tone={airTone}>{state?.air_aqi == null ? airText : `${airText} · AQI ${Math.round(state.air_aqi)}`}</Chip>
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
