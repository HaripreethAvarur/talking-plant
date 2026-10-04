import { useState } from "react";
import { api } from "../api";

const SCENARIOS: [string, string][] = [
  ["dry-to-watered", "💧 Dry, then watered (24 s)"],
  ["dry", "🏜️ Dry soil"],
  ["healthy", "🌿 Healthy"],
  ["dark", "🌑 Dark"],
];

/** Hidden stage controls (Shift+D) in case a real sensor misbehaves during the demo. */
export function DemoPanel({ demoMode, onClose }: { demoMode: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<string>(
    demoMode ? "Ready." : "Scenarios need DEMO_MODE=true in .env (logging works anyway).",
  );

  const run = async (label: string, path: string, body?: object) => {
    setStatus(`${label}…`);
    try {
      const result = await api<Record<string, unknown>>(path, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      const mood = result.mood ?? result.day_mood;
      setStatus(`${label}: done${mood ? ` (${mood})` : ""}.`);
    } catch (e) {
      setStatus(`${label}: ${(e as Error).message}`);
    }
  };

  return (
    <aside className="demo-panel">
      <header>
        <strong>Demo controls</strong>
        <button onClick={onClose} aria-label="Close demo controls">✕</button>
      </header>
      {SCENARIOS.map(([scenario, label]) => (
        <button key={scenario} disabled={!demoMode}
          onClick={() => run(label, "/api/v1/demo/scenario", { scenario })}>
          {label}
        </button>
      ))}
      <button onClick={() => run("📝 Log care now", "/api/v1/care-log/log-now")}>📝 Log care now</button>
      <button onClick={() => run("🌙 Label today", "/api/v1/care-log/label-day")}>🌙 Label today</button>
      <p className="muted">{status}</p>
    </aside>
  );
}
