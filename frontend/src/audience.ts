export type Audience = "5-7" | "8-11" | "12-15";
export const AUDIENCE_KEY = "talking-plant-information-level";
export function readAudience(): Audience {
  try { const value = localStorage.getItem(AUDIENCE_KEY); if (value === "5-7" || value === "12-15") return value; } catch { /* Storage may be unavailable. */ }
  return "8-11";
}
export function saveAudience(value: Audience) { try { localStorage.setItem(AUDIENCE_KEY, value); } catch { /* Keep working in memory. */ } }
