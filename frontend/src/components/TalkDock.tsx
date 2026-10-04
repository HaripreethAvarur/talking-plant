import type { TalkStatus } from "../hooks/usePushToTalk";

interface Props {
  status: TalkStatus;
  error: string | null;
  quickQuestions: string[];
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
export function TalkDock({ status, error, quickQuestions, onMic, onQuestion }: Props) {
  const hint =
    error ??
    (status === "listening"
      ? "I'm all ears! Tap again when you're done."
      : "Pat my leaf or tap the button to talk to me");
  return (
    <section className="dock">
      <button
        className={`mic mic-${status}`}
        onClick={onMic}
        disabled={status === "thinking"}
        aria-label={LABELS[status]}
      >
        <span className="mic-ring" />
        <span className="mic-icon" aria-hidden>{status === "thinking" ? "💭" : "🎤"}</span>
        <span className="mic-label">{LABELS[status]}</span>
      </button>
      <div className="dock-side">
        <p className={`dock-hint ${error ? "dock-error" : ""}`}>{hint}</p>
        <div className="questions">
          {quickQuestions.map((q, i) => (
            <button key={q} className={`chip-q ${CHIP_COLORS[i % CHIP_COLORS.length]}`} onClick={() => onQuestion(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
