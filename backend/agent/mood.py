"""Deterministic observation-time rules. Watering detection lives ONLY here."""

from collections import deque
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from backend.conversation.scripted import MOOD_LINES
from shared.contracts import (
    LeafObservation,
    Light,
    Moisture,
    Mood,
    PlantEvent,
    PlantProfile,
    PlantState,
    SensorReading,
    Source,
    Status,
)

# Moods the plant announces on entry. Grateful is spoken by the watering event instead;
# sleepy and happy are quiet.
SPOKEN_MOODS = (Mood.thirsty, Mood.soggy, Mood.too_dark, Mood.unwell)


class MoodEngine:
    def __init__(self, profile: PlantProfile):
        self.profile = profile
        self.t = profile.thresholds
        self.state = PlantState(plant_id=profile.plant_id)
        self.samples = deque(maxlen=self.t.smoothing_samples)
        self.window = deque(maxlen=3600)
        self.zone = ZoneInfo(profile.timezone)
        self.dry = False
        self.soggy = False
        self.dark = False
        self.unwell = False
        self.dry_candidate = None
        self.soggy_candidate = None
        self.dark_candidate = None
        self.rise_candidate = None
        self.rise_baseline = None
        self.rise_baseline_at = None
        self.grateful_until = None
        self.last_watering = None
        self.armed = True
        self.leaf_count = 0
        self.leaf_direction = None
        self.last_leaf_ok_at = None
        self.identity = None
        self.last_speech = {}

    def _event(self, at, kind, reason, source=Source.backend, observation_id=None, text=None):
        event = PlantEvent(
            plant_id=self.profile.plant_id,
            timestamp=at,
            source=source,
            kind=kind,
            mood=self.state.mood,
            reason=reason,
            observation_id=observation_id,
            suggested_text=text,
        )
        self.state.last_event_id = event.event_id
        return event

    def _reset_continuity(self):
        self.samples.clear()
        self.window.clear()
        self.dry_candidate = self.soggy_candidate = self.dark_candidate = self.rise_candidate = None
        self.rise_baseline = None
        self.rise_baseline_at = None

    def _debounce(self, value, current, enter, leave, candidate_name, seconds, at):
        target = value < leave if current else value <= enter
        if target == current:
            setattr(self, candidate_name, None)
            return current
        since = getattr(self, candidate_name)
        if since is None:
            since = at
            setattr(self, candidate_name, since)
        if (at - since).total_seconds() >= seconds:
            setattr(self, candidate_name, None)
            return target
        return current

    def adopt(self, profile: PlantProfile):
        """Switch to a new profile (e.g. after registration) without losing live state."""
        self.profile, self.t = profile, profile.thresholds
        self.zone = ZoneInfo(profile.timezone)

    def is_night(self, at):
        hour = at.astimezone(self.zone).hour
        start, end = self.t.night_start_hour, self.t.night_end_hour
        return (hour >= start or hour < end) if start > end else start <= hour < end

    def _mood(self, at, source=Source.backend, observation_id=None):
        if self.grateful_until and at < self.grateful_until:
            mood, reason = Mood.grateful, "Sustained moisture rise indicates watering."
        elif self.dry:
            mood, reason = Mood.thirsty, "Calibrated relative moisture stayed below the dry threshold."
        elif self.soggy:
            mood, reason = Mood.soggy, "Relative moisture stayed above the soggy threshold."
        elif self.unwell:
            mood, reason = Mood.unwell, "Repeated leaf color observations exceeded the configured threshold."
        elif self.dark and self.is_night(at):
            mood, reason = Mood.sleepy, "Dark at night is normal; the plant is resting."
        elif self.dark:
            mood, reason = Mood.too_dark, "Ambient light stayed below the threshold during the day."
        else:
            mood, reason = Mood.happy, "No sustained care condition is currently active."
        if mood == self.state.mood:
            return []
        self.state.mood, self.state.reason = mood, reason
        text = MOOD_LINES[mood] if mood in SPOKEN_MOODS else None
        last = self.last_speech.get(mood.value)
        if text and last and (at - last).total_seconds() < self.t.speech_cooldown:
            text = None
        if text:
            self.last_speech[mood.value] = at
        return [self._event(at, "mood_changed", reason, source, observation_id, text)]

    def sensor(self, reading: SensorReading, now: datetime):
        at = reading.timestamp
        if (now - at).total_seconds() > self.t.stale_seconds:
            return "stale", []
        if self.state.last_sensor_at and at <= self.state.last_sensor_at:
            return "out_of_order", []
        identity = (
            reading.source.value,
            reading.device_id,
            reading.moisture.calibration_id,
            reading.session_id,
        )
        if (
            identity != self.identity
            or not self.state.last_sensor_at
            or (at - self.state.last_sensor_at).total_seconds() > self.t.stale_seconds
        ):
            self._reset_continuity()
        self.identity = identity
        previous_health = self.state.sensor_health
        self.state.last_sensor_at = at
        self.state.timestamp = now
        self.state.moisture = reading.moisture
        self.state.light = reading.light
        statuses = (reading.moisture.status, reading.light.status)
        self.state.sensor_health = next(
            (
                s
                for s in (
                    Status.disconnected,
                    Status.error,
                    Status.stale,
                    Status.missing,
                    Status.uncalibrated,
                )
                if s in statuses
            ),
            Status.ok,
        )
        events = []
        if previous_health != self.state.sensor_health:
            events.append(
                self._event(
                    at,
                    "sensor_health",
                    f"Sensor health: {self.state.sensor_health.value}.",
                    reading.source,
                    reading.event_id,
                )
            )
        watered = False
        if reading.moisture.status == Status.ok:
            self.samples.append(reading.moisture.relative_percent)
            value = median(self.samples)
            self.state.smoothed_moisture_percent = value
            self.dry = self._debounce(
                value, self.dry, self.t.dry_enter, self.t.dry_exit, "dry_candidate", self.t.dry_seconds, at
            )
            # Same debounce, mirrored: soggy enters at or above soggy_enter.
            self.soggy = self._debounce(
                -value,
                self.soggy,
                -self.t.soggy_enter,
                -self.t.soggy_exit,
                "soggy_candidate",
                self.t.soggy_seconds,
                at,
            )
            cooling = (
                self.last_watering and (at - self.last_watering).total_seconds() < self.t.watering_cooldown
            )
            if self.dry and not cooling and (not self.grateful_until or at >= self.grateful_until):
                self.armed = True
            while self.window and (at - self.window[0][0]).total_seconds() > self.t.watering_window:
                self.window.popleft()
            baseline_at, baseline = min(self.window, key=lambda sample: sample[1], default=(at, value))
            if self.rise_candidate and (at - self.rise_baseline_at).total_seconds() > self.t.watering_window:
                self.rise_candidate = self.rise_baseline = None
            reference = self.rise_baseline if self.rise_candidate else baseline
            if self.armed and not cooling and value - reference >= self.t.watering_rise:
                if self.rise_candidate is None:
                    self.rise_candidate, self.rise_baseline = at, baseline
                    self.rise_baseline_at = baseline_at
                if (at - self.rise_candidate).total_seconds() >= self.t.watering_sustain:
                    watered = True
                    self.armed = False
                    self.last_watering = at
                    self.grateful_until = at + timedelta(seconds=self.t.grateful_seconds)
                    self.rise_candidate = self.rise_baseline = None
                    self.window.clear()
            else:
                self.rise_candidate = self.rise_baseline = None
            # Establish a full smoothing window before recording a watering baseline.
            if len(self.samples) == self.t.smoothing_samples:
                self.window.append((at, value))
        else:
            self._reset_continuity()
            self.state.smoothed_moisture_percent = None
        if reading.light.status == Status.ok and reading.light.unit == self.t.light_unit:
            self.dark = self._debounce(
                reading.light.value,
                self.dark,
                self.t.dark_enter,
                self.t.dark_exit,
                "dark_candidate",
                self.t.dark_seconds,
                at,
            )
        else:
            self.dark_candidate = None
        events += self._mood(at, reading.source, reading.event_id)
        if watered:
            # Only this event suggests thanks; grateful's mood_changed event is silent.
            events.append(
                self._event(
                    at,
                    "watering",
                    "Sustained relative moisture rise within the watering window.",
                    reading.source,
                    reading.event_id,
                    MOOD_LINES[Mood.grateful],
                )
            )
        return "accepted", events

    def leaf(self, observation: LeafObservation, now: datetime):
        old = self.state.leaf
        if old and observation.timestamp <= old.timestamp:
            return "out_of_order", []
        if (now - observation.timestamp).total_seconds() > self.t.leaf_stale_seconds:
            return "stale", []
        self.state.leaf = observation
        self.state.timestamp = now
        if observation.status != Status.ok:
            self.leaf_count = 0
            return "accepted", []
        self.last_leaf_ok_at = observation.timestamp
        if old and (observation.timestamp - old.timestamp).total_seconds() > self.t.leaf_stale_seconds:
            self.leaf_count = 0
        color = observation.yellow_proportion + observation.brown_proportion
        target = color > self.t.leaf_color_exit if self.unwell else color >= self.t.leaf_color_enter
        self.leaf_count = self.leaf_count + 1 if self.leaf_direction == target else 1
        self.leaf_direction = target
        if self.leaf_count >= self.t.leaf_confirmations:
            self.unwell = target
        return "accepted", self._mood(observation.timestamp, observation.source, observation.event_id)

    def tick(self, now: datetime):
        events = []
        if (
            self.state.last_sensor_at
            and (now - self.state.last_sensor_at).total_seconds() > self.t.stale_seconds
            and self.state.sensor_health != Status.stale
        ):
            self.state.sensor_health = Status.stale
            self.state.moisture = Moisture(status=Status.stale)
            self.state.light = Light(status=Status.stale)
            self.state.smoothed_moisture_percent = None
            self._reset_continuity()
            events.append(self._event(now, "sensor_health", "No fresh sensor reading within the timeout."))
        if self.last_leaf_ok_at and (now - self.last_leaf_ok_at).total_seconds() > self.t.leaf_stale_seconds:
            self.unwell = False
            self.leaf_count = 0
        if self.grateful_until and now >= self.grateful_until:
            self.grateful_until = None
        events += self._mood(now)
        if events:
            self.state.timestamp = now
        return events

    def checkpoint(self):
        """Persist latches/cooldowns; deliberately rebuild continuity after a restart."""
        return {
            "state": self.state.model_dump(mode="json"),
            "dry": self.dry,
            "soggy": self.soggy,
            "dark": self.dark,
            "unwell": self.unwell,
            "armed": self.armed,
            "last_watering": self.last_watering.isoformat() if self.last_watering else None,
            "grateful_until": self.grateful_until.isoformat() if self.grateful_until else None,
            "last_leaf_ok_at": self.last_leaf_ok_at.isoformat() if self.last_leaf_ok_at else None,
            "last_speech": {k: v.isoformat() for k, v in self.last_speech.items()},
        }

    def restore(self, data):
        self.state = PlantState.model_validate(data["state"])
        for name in ("dry", "dark", "unwell", "armed"):
            setattr(self, name, data[name])
        self.soggy = data.get("soggy", False)  # absent in checkpoints from before soggy existed
        for name in ("last_watering", "grateful_until", "last_leaf_ok_at"):
            setattr(self, name, datetime.fromisoformat(data[name]) if data.get(name) else None)
        self.last_speech = {k: datetime.fromisoformat(v) for k, v in data["last_speech"].items()}
