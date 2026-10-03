// Mirror of shared/contracts.py. Keep the two in sync.

export type Mood = "happy" | "thirsty" | "too_dark" | "unwell" | "grateful";

export interface PlantState {
  type: "plant_state";
  mood: Mood;
  message: string | null;
  moisture_pct: number | null;
  light_pct: number | null;
  leaf_issues: string[];
  ts: number;
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

export type ServerMessage = PlantState | SpeechAudio;

export interface Health {
  stt: boolean;
  tts: boolean;
  llm: boolean;
  plant: { name: string; species: string };
  quick_questions: string[];
}
