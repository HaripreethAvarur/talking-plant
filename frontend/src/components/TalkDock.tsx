import { useState } from "react";
import type { TalkStatus } from "../hooks/usePushToTalk";

interface Props {
  status: TalkStatus;
  error: string | null;
  plantName: string;
  wakeWord: boolean;
  quickQuestions: string[];
  disabled?: boolean;
  onMic: () => void;
  onQuestion: (q: string) => void;
}

const LABELS: Record<TalkStatus, string> = {
  idle: "Tap to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  error: "Try again",
};
const CHIP_COLORS = ["chip-q-pink", "chip-q-blue", "chip-q-yellow", "chip-q-purple"];

/** Big tap-to-talk button, quick questions, and how else to start a chat. */
export function TalkDock({ status, error, plantName, wakeWord, quickQuestions, disabled, onMic, onQuestion }: Props) {
  const [more, setMore] = useState(false);
  const hint =
    error ??
    (status === "listening"
      ? "I'm all ears! Tap again when you're done."
      : `Pat my leaf${wakeWord ? ` or say “Hi ${plantName}!”` : ""} to talk to me`);
  return (
    <section className="dock">
      <button
        className={`mic mic-${status}`}
        onClick={onMic}
        disabled={disabled || status === "thinking"}
        aria-label={LABELS[status]}
      >
        <span className="mic-ring" />
        <span className="mic-icon" aria-hidden>{status === "thinking" ? "💭" : "🎤"}</span>
        <span className="mic-label">{status === "idle" ? `Talk to ${plantName}` : LABELS[status]}</span>
      </button>
      <div className="dock-side">
        <p className={`dock-hint ${error ? "dock-error" : ""}`}>{hint}</p>
        <div className="questions">
          {(more ? quickQuestions : quickQuestions.slice(0, 2)).map((q, i) => (
            <button key={q} className={`chip-q ${CHIP_COLORS[i % CHIP_COLORS.length]}`} disabled={disabled || status !== "idle" && status !== "error"} onClick={() => onQuestion(q)}>
              {q}
            </button>
          ))}
          {quickQuestions.length > 2 && <button className="more-questions" aria-expanded={more} onClick={() => setMore(!more)}>{more ? "Fewer questions" : "More questions"}</button>}
        </div>
      </div>
    </section>
  );
}
