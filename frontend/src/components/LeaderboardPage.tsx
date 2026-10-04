import { useEffect, useState } from "react";
import { api } from "../api";
import type { Leaderboard, LeaderboardEntry, PlantType } from "../contracts";

const EMOJI: Record<PlantType, string> = { succulent: "🌵", plant: "🪴", tree: "🌳" };
const PODIUM_ORDER = [1, 0, 2]; // second, first, third

function Suns({ days, of }: { days: number; of: number }) {
  return (
    <span className="suns" aria-label={`${days} happy days out of ${of}`}>
      {Array.from({ length: of }, (_, i) => (
        <span key={i} className={i < days ? "sun-on" : "sun-off"}>{i < days ? "☀️" : "•"}</span>
      ))}
    </span>
  );
}

function Podium({ entries, you }: { entries: LeaderboardEntry[]; you: string | null }) {
  return (
    <div className="podium">
      {PODIUM_ORDER.map((index) => {
        const entry = entries[index];
        if (!entry) return <div key={index} className="podium-spot podium-empty" />;
        return (
          <div key={entry.username} className={`podium-spot place-${index + 1} ${entry.username === you ? "is-you" : ""}`}>
            {index === 0 && <span className="crown" aria-hidden>👑</span>}
            <span className="podium-plant" aria-hidden>{EMOJI[entry.plant_type]}</span>
            <strong className="podium-name">{entry.plant_name}</strong>
            <span className="podium-kid">{entry.username}</span>
            <div className="podium-block">
              <span className="podium-rank">{entry.rank}</span>
              <span className="podium-days">{entry.happy_days} ☀️</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Its own tab: the week's happiest plants, everywhere. */
export function LeaderboardPage() {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api<Leaderboard>("/api/leaderboard?limit=50").then(setBoard).catch((e: Error) => setError(e.message));
    load();
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, []);

  const mine = board?.entries.find((e) => e.username === board.you);

  return (
    <main className="board-page">
      <header className="board-hero">
        <h2>🏆 Happiest Plants This Week</h2>
        <p>Every happy day earns a sunshine ☀️ — can your plant get all 7?</p>
      </header>
      {error && <p className="card board-message">{error}</p>}
      {!board && !error && <p className="card board-message">Counting sunshine… ☀️</p>}
      {board && board.entries.length === 0 && <p className="card board-message">No plants yet. Yours could be first! 🌱</p>}
      {board && board.entries.length > 0 && (
        <div className="board-layout">
          <Podium entries={board.entries.slice(0, 3)} you={board.you} />
          <div className="board-side">
            {mine && (
              <div className="card my-score">
                <span className="my-score-plant" aria-hidden>{EMOJI[mine.plant_type]}</span>
                <div>
                  <strong>{mine.plant_name} is #{mine.rank}!</strong>
                  <Suns days={mine.happy_days} of={board.days} />
                </div>
              </div>
            )}
            <ol className="card board-list">
              {board.entries.map((entry) => (
                <li key={entry.username} className={entry.username === board.you ? "is-you" : ""}>
                  <span className="list-rank">{entry.rank}</span>
                  <span className="list-plant" aria-hidden>{EMOJI[entry.plant_type]}</span>
                  <span className="list-name">
                    <strong>{entry.plant_name}</strong>
                    <small>{entry.username} · {entry.location}</small>
                  </span>
                  <Suns days={entry.happy_days} of={board.days} />
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </main>
  );
}
