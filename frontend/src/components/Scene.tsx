import type { Face } from "../contracts";

const STARS = Array.from({ length: 28 }, (_, i) => ({
  left: (i * 37) % 100,
  top: (i * 53) % 46,
  size: 3 + (i % 3) * 2,
  delay: (i % 7) * 0.4,
}));
const DROPS = Array.from({ length: 22 }, (_, i) => ({ left: 4 + ((i * 41) % 92), delay: (i % 9) * 0.17 }));
const CONFETTI = Array.from({ length: 36 }, (_, i) => ({
  left: (i * 29) % 100,
  delay: (i % 12) * 0.12,
  color: ["#ff5fa2", "#ffd23f", "#5bc8f5", "#7ed957", "#8b5cf6", "#ff8a1f"][i % 6],
  turn: (i % 2 ? 1 : -1) * (180 + (i % 5) * 90),
}));

function Cloud({ className }: { className: string }) {
  return (
    <svg className={`cloud ${className}`} viewBox="0 0 220 120">
      <path d="M46 108 C14 108 8 66 40 60 C40 28 86 18 104 42 C116 10 172 14 172 52 C206 50 214 106 178 108 Z" />
    </svg>
  );
}

/**
 * The animated world behind the app. Day or night follows the real clock at the plant's
 * location (`night`, from sunrise/sunset), clouds and rain follow the real weather there, and
 * the rest (rainbow, hot sun, hills) follows the plant's mood.
 */
export function Scene({
  face,
  night: isNight,
  weatherCode,
  lightPct,
}: {
  face: Face;
  night?: boolean | null;
  weatherCode?: number | null;
  lightPct?: number | null;
}) {
  const night = isNight ?? (face === "sleepy" || face === "too_dark");
  // Real weather outside: drizzle/rain/showers/storms (WMO 51-67, 80-82, 95-99), and cloud or fog.
  const code = weatherCode ?? -1;
  const rainingOutside = (code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code >= 95;
  const cloudyOutside = code === 3 || code === 45 || code === 48;
  const rainy = face === "soggy" || rainingOutside;
  // A dark room in the daytime turns the sky gloomy right away, before the mood catches up.
  const gloomy = !night && (face === "too_dark" || (lightPct != null && lightPct < 12));
  const overcast = rainy || cloudyOutside || gloomy || face === "offline";
  return (
    <div className={`scene scene-${face} ${night ? "scene-night" : gloomy ? "scene-gloomy" : ""}`} aria-hidden>
      {night ? (
        <>
          {STARS.map((s, i) => (
            <span key={i} className="star" style={{ left: `${s.left}%`, top: `${s.top}%`, width: s.size, height: s.size, animationDelay: `${s.delay}s` }} />
          ))}
          <div className="moon" />
        </>
      ) : overcast ? null : (
        <div className={`sun ${face === "thirsty" ? "sun-hot" : ""}`}>
          <div className="sun-rays" />
          <div className="sun-core" />
        </div>
      )}
      {face === "grateful" && <div className="rainbow" />}
      <Cloud className={`cloud-1 ${rainy ? "cloud-rain" : ""}`} />
      <Cloud className={`cloud-2 ${rainy ? "cloud-rain" : ""}`} />
      {!night && <Cloud className="cloud-3" />}
      {rainy &&
        DROPS.map((d, i) => <span key={i} className="raindrop" style={{ left: `${d.left}%`, animationDelay: `${d.delay}s` }} />)}
      {face === "grateful" &&
        CONFETTI.map((c, i) => (
          <span
            key={i}
            className="confetti"
            style={{ left: `${c.left}%`, background: c.color, animationDelay: `${c.delay}s`, ["--turn" as string]: `${c.turn}deg` }}
          />
        ))}
      <svg className="hills" viewBox="0 0 1440 260" preserveAspectRatio="none">
        <path className="hill-back" d="M0 120 C220 40 420 60 640 110 C860 160 1080 50 1440 100 V260 H0 Z" />
        <path className="hill-front" d="M0 180 C260 120 520 150 760 190 C1000 230 1220 140 1440 170 V260 H0 Z" />
      </svg>
    </div>
  );
}
