import type { TalkStatus } from "../hooks/usePushToTalk";

interface Props {
  status: TalkStatus;
  error: string | null;
  sttAvailable: boolean;
  quickQuestions: string[];
  onPressStart: () => void;
  onPressEnd: () => void;
  onQuestion: (q: string) => void;
}

const LABELS: Record<TalkStatus, string> = {
  idle: "Hold to talk",
  listening: "Listening…",
  thinking: "Thinking…",
  error: "Hold to try again",
};

/** Push-to-talk button (Task 3) plus question buttons as the no-microphone fallback. */
export function TalkPanel({ status, error, sttAvailable, quickQuestions, onPressStart, onPressEnd, onQuestion }: Props) {
  return (
    <div className="talk-panel">
      <button
          className={`talk-button talk-${status}`}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            onPressStart();
          }}
          onPointerUp={onPressEnd}
          onPointerCancel={onPressEnd}
          onContextMenu={(e) => e.preventDefault()}
          disabled={status === "thinking"}
        >
          <span aria-hidden>🎤</span> {LABELS[status]}
      </button>
      <p className="talk-hint">{error ?? (status === "listening" ? "I'm listening. Recording stops automatically." : sttAvailable ? "or pat the touch sensor to ask a question" : "Voice recognition is offline. You can still test the microphone or tap a question.")}</p>
      <div className="quick-questions">
        {quickQuestions.map((q) => (
          <button key={q} className="quick-question" onClick={() => onQuestion(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
