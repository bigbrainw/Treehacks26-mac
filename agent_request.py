"""
Build the JSON request sent to the focus agent when help is triggered.

Single source of truth for the agent request format.
"""
import time
from typing import Any, Optional

from data_schema import ActivitySnapshot, MentalStateSnapshot


def build_agent_request(
    activity: ActivitySnapshot,
    mental_state: Optional[MentalStateSnapshot],
    user_feedback: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> dict:
    """
    Build the canonical request payload sent to the agent.

    Used for:
    - WebSocket `reading_help` messages
    - HTTP POST /eeg body (wrapped in `context` + `streams`)

    Returns a dict suitable for json.dumps().
    """
    t = timestamp if timestamp is not None else time.time()

    mental_state_data: Optional[dict] = None
    if mental_state:
        mental_state_data = {
            "engagement": mental_state.engagement,
            "stress": mental_state.stress,
            "relaxation": mental_state.relaxation,
            "focus": mental_state.focus,
            "excitement": mental_state.excitement,
            "interest": mental_state.interest,
            "metrics": mental_state.metrics,
        }

    return {
        "timestamp": t,
        "activity": {
            "app_name": activity.app_name,
            "window_title": activity.window_title,
            "context_type": activity.context_type,
            "context_id": activity.context_id,
            "reading_section": activity.reading_section,
            "duration_seconds": activity.duration_seconds,
        },
        "mental_state": mental_state_data,
        "user_feedback": user_feedback,
    }


def build_reading_help_ws_message(request: dict) -> dict:
    """Wrap agent request for WebSocket reading_help type."""
    return {"type": "reading_help", **request}


def build_post_eeg_body(request: dict, streams_met: Optional[dict] = None) -> dict:
    """Wrap agent request for HTTP POST /eeg body."""
    body = {
        "timestamp": request["timestamp"],
        "streams": {"met": streams_met or {}},
        "context": {
            "app_name": request["activity"]["app_name"],
            "window_title": request["activity"]["window_title"],
            "context_type": request["activity"]["context_type"],
            "context_id": request["activity"]["context_id"],
            "reading_section": request["activity"].get("reading_section"),
            "duration_seconds": request["activity"]["duration_seconds"],
            "mental_state": request["mental_state"],
            "user_feedback": request["user_feedback"],
        },
    }
    return body
