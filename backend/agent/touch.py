"""Touch arms on release; one rising edge starts one bounded listening window."""

from datetime import datetime

from shared.contracts import Status


class TouchGate:
    def __init__(self, cooldown, debounce, stale):
        self.cooldown, self.debounce, self.stale = cooldown, debounce, stale
        self.identity = None
        self.last_at = None
        self.last_triggered = None
        self.released_at = None
        self.pressed = None

    def observe(self, observation, now):
        at = observation.timestamp
        if (now - at).total_seconds() > self.stale:
            return "stale", False
        if self.last_at and at <= self.last_at:
            return "out_of_order", False
        identity = (observation.source, observation.device_id, observation.session_id)
        if identity != self.identity or (self.last_at and (at - self.last_at).total_seconds() > self.stale):
            self.pressed = self.released_at = None
        self.identity, self.last_at = identity, at
        if observation.status != Status.ok:
            self.pressed = self.released_at = None
            return "accepted", False
        previous = self.pressed
        self.pressed = observation.pressed
        if not self.pressed:
            if previous is not False:
                self.released_at = at
            return "accepted", False
        # An initially held sensor or reconnect while held must not open a microphone.
        eligible = previous is False and self.released_at is not None
        eligible = eligible and (at - self.released_at).total_seconds() >= self.debounce
        eligible = eligible and (
            not self.last_triggered or (at - self.last_triggered).total_seconds() >= self.cooldown
        )
        if eligible:
            self.last_triggered = at
        return "accepted", bool(eligible)

    def restore(self, checkpoint):
        # Rebuild release/press continuity after restart, retaining cooldown only.
        value = checkpoint.get("last_triggered")
        self.last_triggered = datetime.fromisoformat(value) if value else None

    def checkpoint(self):
        return {"last_triggered": self.last_triggered.isoformat() if self.last_triggered else None}
