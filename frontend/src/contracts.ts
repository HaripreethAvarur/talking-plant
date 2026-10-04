// Mirror of the UI messages in shared/contracts.py (schemas in shared/schemas/). Keep in sync.

export type Mood = "happy" | "thirsty" | "too_dark" | "unwell" | "grateful";

export interface PlantState {
  type: "plant_state";
  mood: Mood;
  message: string | null;
  moisture_pct: number | null;
  light_pct: number | null;
  leaf_issues: string[] | null; // null: the camera has no recent look
  ts: number;
  sensor_health?: string;
  light_value?: number | null;
  light_unit?: "raw" | "lux" | null;
}

export interface SpeechAudio {
  type: "speech_audio";
  text: string;
  audio_url: string | null;
  mime: string;
  cached: boolean;
  ts: number;
}

export interface ChildUtterance {
  type: "child_utterance";
  text: string;
  source: "stt" | "button" | "typed";
  ts: number;
}

export interface ListenRequest {
  type: "listen_request";
  schema_version: "1.0";
  event_id: string;
  plant_id: string;
  timestamp: string;
  duration_ms: number;
}

export type ServerMessage = PlantState | SpeechAudio | ListenRequest;

export interface Health {
  stt: boolean;
  tts: boolean;
  llm: boolean;
  plant: { name: string; species: string };
  quick_questions: string[];
}
