import { useEffect, useState } from "react";
import type { Face } from "../contracts";

export type DayPhase = "morning" | "day" | "evening" | "night";
export function dayPhase(date: Date, timezone?: string): DayPhase {
  let hour = date.getHours();
  if (timezone) { try { hour = Number(new Intl.DateTimeFormat("en-US", { timeZone: timezone, hour: "numeric", hourCycle: "h23" }).format(date)); } catch { /* Fall back to browser local time. */ } }
  return hour < 6 || hour >= 20 ? "night" : hour < 10 ? "morning" : hour < 17 ? "day" : "evening";
}
/** Clock-driven scenery; mood accents never claim to show actual weather. */
export function Scene({ face, timezone }: { face: Face; timezone?: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 60000); return () => clearInterval(timer); }, []);
  const phase = dayPhase(now, timezone);
  useEffect(() => { document.documentElement.dataset.dayPhase = phase; return () => { delete document.documentElement.dataset.dayPhase; }; }, [phase]);
  return <div className={`scene garden-scene scene-${face} phase-${phase}`} aria-hidden>
    <div className="garden-halo" />
    <div className={phase === "night" ? "garden-moon" : "garden-sun"} />
    {phase === "night" && Array.from({length:12}, (_,i) => <i key={i} className="garden-star" style={{left:`${10+(i*17)%80}%`,top:`${12+(i*13)%40}%`}} />)}
    <svg className="garden-hills" viewBox="0 0 1440 250" preserveAspectRatio="none"><path d="M0 110 Q240 20 480 100 T960 90 T1440 95 V250 H0Z" /><path d="M0 170 Q300 100 640 170 T1440 150 V250 H0Z" /></svg>
    <div className="garden-ground" />
  </div>;
}
