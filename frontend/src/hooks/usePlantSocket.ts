import { useCallback, useEffect, useRef, useState } from "react";
import { viewerToken } from "../api";
import type { ChildUtterance, ListenRequest, PlantState, ServerMessage, SpeechAudio } from "../contracts";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

/** Live connection to the backend /ws; reconnects on its own if the backend restarts. */
export function usePlantSocket(onAudio: (audio: SpeechAudio) => void, onListen?: (request: ListenRequest) => void) {
  const [state, setState] = useState<PlantState | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onAudioRef = useRef(onAudio);
  onAudioRef.current = onAudio;
  const onListenRef = useRef(onListen);
  onListenRef.current = onListen;
  const seen = useRef(new Set<string>());

  useEffect(() => {
    let closed = false;
    let retryMs = 500;
    let timer: number | undefined;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => {
        const token = viewerToken();
        if (token) ws.send(JSON.stringify({ type: "auth", token }));
        setConnected(true);
        retryMs = 500;
      };
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as ServerMessage;
        if (msg.type === "plant_state") setState(msg);
        else if (msg.type === "speech_audio") onAudioRef.current(msg);
        else if (msg.type === "listen_request") {
          const age = Date.now() - Date.parse(msg.timestamp);
          if (!Number.isFinite(age) || age < -5000 || age > 5000 || seen.current.has(msg.event_id)) return;
          seen.current.add(msg.event_id);
          if (seen.current.size > 1000) seen.current.delete(seen.current.values().next().value!);
          onListenRef.current?.(msg);
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (closed) return;
        timer = window.setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, 5000);
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, []);

  const sendUtterance = useCallback((text: string, source: ChildUtterance["source"]) => {
    const msg: ChildUtterance = { type: "child_utterance", text, source, ts: Date.now() / 1000 };
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
      return true;
    }
    return false;
  }, []);

  return { state, connected, sendUtterance };
}
