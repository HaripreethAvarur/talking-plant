// Mirror of the UI messages in shared/contracts.py (schemas in shared/schemas/). Keep in sync.

export type Mood = "happy" | "thirsty" | "soggy" | "too_dark" | "sleepy" | "unwell" | "grateful";

/** What the character shows: a mood, or "offline" while the sensors aren't reporting. */
export type Face = Mood | "offline";

export interface PlantState {
  type: "plant_state";
  mood: Mood;
  message: string | null;
  moisture_pct: number | null;
  light_pct: number | null;
  leaf_issues: string[] | null; // null: the camera has no recent look
  looks?: string | null; // the camera's latest description of the plant
  looks_at?: number | null; // when that photo was taken (epoch seconds)
  air_aqi?: number | null; // outdoor US AQI for the plant's ZIP code
  checkup_mood?: Mood | null; // ASI's label at the latest care-log checkup
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
  registered?: boolean;
  username?: string | null;
  database?: boolean;
  thresholds?: { dry: number; soggy: number };
  quick_questions: string[];
  demo_mode?: boolean;
}

export type PlantType = "succulent" | "plant" | "tree";

export interface PlantRegistration {
  username: string;
  plant_name: string;
  plant_type: PlantType;
  location: string; // US ZIP code
}

export interface LeaderboardEntry {
  rank: number;
  username: string;
  plant_name: string;
  plant_type: PlantType;
  location: string;
  happy_days: number;
  score: number;
}

export interface Leaderboard {
  days: number;
  you: string | null;
  entries: LeaderboardEntry[];
}
