import { useEffect, useState } from "react";
import { api } from "../api";
import type { Leaderboard, PlantType } from "../contracts";

const EMOJI: Record<PlantType, string> = { succulent: "🌵", plant: "🪴", tree: "🌳" };
const MEDALS = ["🥇", "🥈", "🥉"];

/** Global board: happy days in the last 7 (refreshed each time it opens). */
export function LeaderboardPanel({ onClose }: { onClose: () => void }) {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Leaderboard>("/api/leaderboard").then(setBoard).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="overlay" onClick={onClose}>
      <section className="card leaderboard" onClick={(e) => e.stopPropagation()}>
        <h2>🏆 Happiest plants this week</h2>
        <p className="muted">One point for every happy day in the last 7 days.</p>
        {error && <p className="form-error">{error}</p>}
        {!board && !error && <p className="muted">Loading…</p>}
        {board && board.entries.length === 0 && <p className="muted">No plants yet. Be the first!</p>}
        {board && board.entries.length > 0 && (
          <ol className="board">
            {board.entries.map((entry) => (
              <li key={entry.username} className={entry.username === board.you ? "board-you" : ""}>
                <span className="board-rank">{MEDALS[entry.rank - 1] ?? entry.rank}</span>
                <span className="board-plant">
                  {EMOJI[entry.plant_type]} <strong>{entry.plant_name}</strong>
                  <small> {entry.username} · {entry.location}</small>
                </span>
                <span className="board-days" aria-label={`${entry.happy_days} happy days out of ${board.days}`}>
                  {"☀️".repeat(entry.happy_days)}
                  <span className="board-empty">{"○".repeat(board.days - entry.happy_days)}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
        <button className="big-button" onClick={onClose}>Back to my plant</button>
      </section>
    </div>
  );
}
