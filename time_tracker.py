"""Track time spent in each activity context. Fires warn/long/follow-up events."""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

# ActivityContext is from activity module
from activity import ActivityContext


class SessionEventType(Enum):
    WARN_THRESHOLD = "warn"
    LONG_THRESHOLD = "long"
    FOLLOW_UP = "follow_up"


@dataclass
class SessionEvent:
    context: ActivityContext
    event_type: SessionEventType
    duration_seconds: float


@dataclass
class TrackedSession:
    context_id: str
    context: ActivityContext
    started_at: float

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.started_at


class SessionTracker:
    """
    Tracks how long the user stays in each context.
    Fires events at warn_sec, long_sec, and optionally follow-up intervals.
    """

    def __init__(
        self,
        warn_threshold_sec: float = 20,
        long_threshold_sec: float = 30,
        follow_up_interval_sec: float = 30,
    ):
        self.warn_threshold_sec = warn_threshold_sec
        self.long_threshold_sec = long_threshold_sec
        self.follow_up_interval_sec = follow_up_interval_sec
        self._callbacks: list[Callable[[SessionEvent], None]] = []
        self._current: Optional[TrackedSession] = None
        self._last_long_at: float = 0
        self._last_follow_up_at: float = 0

    def on_session_event(self, callback: Callable[[SessionEvent], None]):
        self._callbacks.append(callback)

    def update(self, ctx: Optional[ActivityContext]) -> None:
        """Call periodically with current context. Fires events when thresholds hit."""
        if ctx is None:
            return

        now = time.time()
        context_id = ctx.context_id

        if self._current is None or self._current.context_id != context_id:
            self._current = TrackedSession(context_id=context_id, context=ctx, started_at=now)
            self._last_long_at = 0
            self._last_follow_up_at = 0
            return

        dur = self._current.duration_seconds

        # Warn threshold (fire once per session)
        if dur >= self.warn_threshold_sec and dur < self.warn_threshold_sec + 0.5:
            self._emit(SessionEvent(ctx, SessionEventType.WARN_THRESHOLD, dur))

        # Long threshold (fire once, then start follow-ups)
        if dur >= self.long_threshold_sec:
            if self._last_long_at == 0:
                self._last_long_at = now
                self._emit(SessionEvent(ctx, SessionEventType.LONG_THRESHOLD, dur))

            # Follow-ups every follow_up_interval_sec after long threshold
            if self.follow_up_interval_sec > 0:
                if self._last_follow_up_at == 0:
                    self._last_follow_up_at = now  # Start count from first long
                else:
                    elapsed = now - self._last_follow_up_at
                    if elapsed >= self.follow_up_interval_sec:
                        self._last_follow_up_at = now
                        self._emit(SessionEvent(ctx, SessionEventType.FOLLOW_UP, dur))

    def _emit(self, event: SessionEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def get_current_session(self) -> Optional[TrackedSession]:
        return self._current
