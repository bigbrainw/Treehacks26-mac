"""Payload schema for collector → Jetson."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EEGMetricsSnapshot:
    """Performance metrics (met stream)."""
    metrics: dict = field(default_factory=dict)


@dataclass
class MentalStateSnapshot:
    """Mental/cognitive state from met (engagement, stress, focus, etc.). Used by agent for feedback."""
    engagement: Optional[float] = None
    stress: Optional[float] = None
    relaxation: Optional[float] = None
    focus: Optional[float] = None
    excitement: Optional[float] = None
    interest: Optional[float] = None
    metrics: dict = field(default_factory=dict)  # raw met for full detail


@dataclass
class MentalCommandSnapshot:
    """Mental command (com stream: push, pull, etc.). Reserved for restaurant suggestions."""
    action: str = "neutral"
    power: float = 0.0


@dataclass
class ActivitySnapshot:
    """Current activity context."""
    app_name: str = ""
    window_title: str = ""
    context_type: str = ""
    context_id: str = ""
    reading_section: Optional[str] = None
    duration_seconds: Optional[float] = None  # time on this context (for reading-help)


@dataclass
class CollectorPayload:
    """Payload sent to Jetson via WebSocket."""
    type: str  # "eeg" | "mental_state" | "mental_command" | "activity"
    timestamp: float = 0.0
    eeg: Optional[EEGMetricsSnapshot] = None
    mental_state: Optional[MentalStateSnapshot] = None
    mental_command: Optional[MentalCommandSnapshot] = None  # for restaurant suggestions only
    activity: Optional[ActivitySnapshot] = None

    def to_dict(self) -> dict:
        d = {"type": self.type, "timestamp": self.timestamp}
        if self.eeg:
            d["eeg"] = {"metrics": self.eeg.metrics}
        if self.mental_state:
            ms = self.mental_state
            d["mental_state"] = {
                "engagement": ms.engagement, "stress": ms.stress, "relaxation": ms.relaxation,
                "focus": ms.focus, "excitement": ms.excitement, "interest": ms.interest,
                "metrics": ms.metrics,
            }
        if self.mental_command:
            d["mental_command"] = {"action": self.mental_command.action, "power": self.mental_command.power}
        if self.activity:
            d["activity"] = {
                "app_name": self.activity.app_name,
                "window_title": self.activity.window_title,
                "context_type": self.activity.context_type,
                "context_id": self.activity.context_id,
                "reading_section": self.activity.reading_section,
                "duration_seconds": self.activity.duration_seconds,
            }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CollectorPayload":
        """Parse from JSON (for Jetson processor)."""
        eeg = None
        if d.get("eeg"):
            m = d["eeg"].get("metrics", d["eeg"]) if isinstance(d["eeg"], dict) else {}
            eeg = EEGMetricsSnapshot(metrics=m)

        ms = None
        if d.get("mental_state"):
            ms_d = d["mental_state"] if isinstance(d["mental_state"], dict) else {}
            ms = MentalStateSnapshot(
                engagement=ms_d.get("engagement"), stress=ms_d.get("stress"),
                relaxation=ms_d.get("relaxation"), focus=ms_d.get("focus"),
                excitement=ms_d.get("excitement"), interest=ms_d.get("interest"),
                metrics=ms_d.get("metrics", {}),
            )

        mc = None
        if d.get("mental_command"):
            mc_d = d["mental_command"] if isinstance(d["mental_command"], dict) else {}
            mc = MentalCommandSnapshot(
                action=mc_d.get("action", "neutral"),
                power=float(mc_d.get("power", 0)),
            )

        act = None
        if d.get("activity"):
            a = d["activity"] if isinstance(d["activity"], dict) else {}
            dur = a.get("duration_seconds")
            act = ActivitySnapshot(
                app_name=a.get("app_name", ""),
                window_title=a.get("window_title", ""),
                context_type=a.get("context_type", ""),
                context_id=a.get("context_id", ""),
                reading_section=a.get("reading_section"),
                duration_seconds=float(dur) if dur is not None else None,
            )

        return cls(
            type=d.get("type", ""),
            timestamp=float(d.get("timestamp", 0)),
            eeg=eeg,
            mental_state=ms,
            mental_command=mc,
            activity=act,
        )
