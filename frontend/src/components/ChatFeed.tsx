import { useEffect, useRef } from "react";

export interface ChatMessage {
  id: number;
  from: "plant" | "kid";
  text: string;
}

interface Props {
  messages: ChatMessage[];
  plantName: string;
  thinking: boolean;
  hint: string;
}

/** The conversation, chat-app style: the plant on the left, the child on the right. */
export function ChatFeed({ messages, plantName, thinking, hint }: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking]);

  return (
    <section className="chat card" aria-live="polite" aria-label={`Chat with ${plantName}`}>
      <header className="card-title">
        <span className="title-icon bg-pink">💬</span> Chat with {plantName}
      </header>
      <div className="chat-scroll">
        {messages.length === 0 && !thinking && <p className="chat-empty">{hint}</p>}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg-${m.from}`}>
            <span className="msg-avatar" aria-hidden>{m.from === "plant" ? "🌱" : "🧒"}</span>
            <p className="msg-bubble">
              <span className="msg-who">{m.from === "plant" ? plantName : "You"}</span>
              {m.text}
            </p>
          </div>
        ))}
        {thinking && (
          <div className="msg msg-plant">
            <span className="msg-avatar" aria-hidden>🌱</span>
            <p className="msg-bubble typing" aria-label={`${plantName} is thinking`}>
              <i /><i /><i />
            </p>
          </div>
        )}
        <div ref={end} />
      </div>
    </section>
  );
}
