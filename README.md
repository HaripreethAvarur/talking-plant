# talking-plant

A plant that talks to kids: sensors and a camera tell it how it feels, a Fetch.ai
agent decides its mood, ASI:One words its replies, ElevenLabs gives it a voice,
and a React character shows its face.

## Layout

| Path | What | Task |
| --- | --- | --- |
| `shared/contracts.py` | JSON messages every part exchanges (`SensorReading`, `LeafObservation`, `ChildUtterance`, `PlantState`, `SpeechAudio`) | 0 |
| `backend/sensors/` | FreeWILi sensor reader | 1 |
| `backend/vision/` | Leaf stress checker | 2 |
| `backend/speech/stt.py` | Child speech-to-text (ElevenLabs) | 3 |
| `backend/agent/` | Plant Care Agent and mood engine (Fetch.ai) | 4 |
| `backend/conversation/` | Grounded, kid-safe replies (ASI:One) with scripted fallback | 5 |
| `backend/database/` | Plant profile and care history (Neon) | 6 |
| `backend/speech/tts.py` | Plant voice (ElevenLabs) with an offline cache | 7 |
| `frontend/` | React character UI | 8 |
| `backend/server.py` | WebSocket bridge between the agent and the UI | 8 |
| `backend/mock_agent.py` | Stand-in for the agent; replays "dry, then watered" | 0 / 4 |

## Run it

```sh
cp .env.example .env               # fill in keys; placeholders switch on the fallbacks
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

python -m backend.server           # terminal 1: UI bridge on :8000
cd frontend && npm run dev         # terminal 2: open http://localhost:5173
python -m backend.mock_agent       # terminal 3: replay the demo sequence (--loop to repeat)
```

Click "Tap to wake up" once; browsers need a click before they will play sound.

## Integrating with the bridge

- **Agent (Task 4):** `POST /api/plant-state` with a `PlantState`. If it has a
  `message`, the plant speaks it. For the scripted mood lines, use
  `backend.conversation.scripted.MOOD_LINES`.
- **Child questions:** the UI sends `ChildUtterance` over `/ws`. The bridge answers with
  `backend.conversation.replies.reply()`, grounded in the latest `PlantState`.
- **History (Task 6):** `Hub.history` in `backend/server.py` is in memory for now.
  Replace it with rows from Neon.

## Fallbacks (no keys or no network)

| Piece | Fallback |
| --- | --- |
| Speech-to-text | The talk button hides; on-screen question buttons send the question instead |
| ASI:One | Scripted replies by intent and mood, filled with real readings |
| Unsafe or ungrounded LLM output | Rejected by `conversation/safety.py`, then scripted reply |
| ElevenLabs TTS | Cached clip if one exists, else the browser's speech synthesis |

Before the demo, with a real key, cache every fixed line so they play offline:

```sh
python -m backend.speech.pregenerate
```

## Checks

```sh
python -m unittest discover -s backend/tests -t .   # offline tests for Tasks 3, 5, 7
python -m backend.conversation.try_questions        # 10 sample questions (Task 5)
cd frontend && npm run build                        # type-check and build the UI
```
