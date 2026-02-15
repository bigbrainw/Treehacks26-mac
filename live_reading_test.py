#!/usr/bin/env python3
"""
Live reading-context test: uses REAL activity (what you're reading now), time on page, mental state.
When you stay on difficult content too long, triggers Jetson agent for help.

Usage:
  python live_reading_test.py                    # live, 30s threshold
  python live_reading_test.py --long 45           # 45 sec on page before trigger
  python live_reading_test.py --mental distracted # simulate distracted state
  python live_reading_test.py --warn 15 --long 30 # warn at 15s, trigger at 30s
"""
import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from activity import ActivityMonitor
from feedback_window import FeedbackWindow
from time_tracker import SessionTracker, SessionEvent, SessionEventType

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


def _post_for_help(
    jetson_url: str,
    ctx,
    duration_seconds: float,
    mental_state: str,
    user_feedback: str | None,
) -> str | None:
    """POST to Jetson /eeg with context + duration + mental_state. Returns feedback string."""
    if not _REQUESTS_AVAILABLE:
        return None
    context = ctx.to_dict() if hasattr(ctx, "to_dict") else {}
    context["duration_seconds"] = duration_seconds
    context["mental_state"] = mental_state
    if user_feedback:
        context["user_feedback"] = user_feedback
    body = {
        "timestamp": time.time(),
        "streams": {"met": {"met": [True, 0.4, True, 0.5, 0.4, True, 0.5], "time": time.time()}},
        "context": context,
    }
    try:
        r = requests.post(
            jetson_url,
            json=body,
            headers={"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"},
            timeout=15,
        )
        if r.status_code == 200 and r.text:
            data = r.json()
            return data.get("feedback") or data.get("message")
    except Exception:
        pass
    return None


def run_live(
    jetson_url: str,
    mental_state: str = "stuck",
    warn_sec: float = 20,
    long_sec: float = 30,
    poll_interval: float = 0.3,
) -> None:
    """Run live: real activity, time on page, Jetson on long threshold."""
    activity = ActivityMonitor(poll_interval=poll_interval)
    session_tracker = SessionTracker(
        warn_threshold_sec=warn_sec,
        long_threshold_sec=long_sec,
        follow_up_interval_sec=max(30, long_sec // 2),
    )

    feedback_window = FeedbackWindow()
    feedback_window.update_feedback("Monitoring... Stay on a difficult page to trigger help.")

    def on_session_event(event: SessionEvent):
        if event.event_type not in (SessionEventType.LONG_THRESHOLD, SessionEventType.FOLLOW_UP):
            return
        user_feedback = (
            "(Still on this – try a different angle)"
            if event.event_type == SessionEventType.FOLLOW_UP
            else None
        )
        print(f"[{event.event_type.value}] {event.duration_seconds:.0f}s on: {event.context.display_name}")
        feedback = _post_for_help(
            jetson_url,
            event.context,
            event.duration_seconds,
            mental_state,
            user_feedback,
        )
        if feedback:
            feedback_window.update_feedback(feedback)
            print(f"  >>> {feedback[:80]}...")
        else:
            feedback_window.update_feedback("(No response from Jetson – check connection)")

    session_tracker.on_session_event(on_session_event)

    running = True

    def stop(_=None, __=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    feedback_window.root.protocol("WM_DELETE_WINDOW", lambda: (stop(), feedback_window.root.destroy()))

    def poll_loop():
        while running:
            ctx = activity.get_current_activity()
            session_tracker.update(ctx)
            time.sleep(poll_interval)

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()

    print("\n--- Live Reading Test ---")
    print(f"  Jetson: {jetson_url}")
    print(f"  Mental state: {mental_state}")
    print(f"  Triggers: warn={warn_sec}s, long={long_sec}s")
    print("  Stay on a difficult page to get help. Ctrl+C or close window to stop.\n")

    feedback_window.run()


def main():
    p = argparse.ArgumentParser(
        description="Live reading-context test: real activity, time on page, Jetson agent"
    )
    p.add_argument("--url", default=None, help="Jetson base URL (default: from config)")
    p.add_argument("--mental", default="stuck", choices=["stuck", "distracted", "focused"])
    p.add_argument("--warn", type=float, default=20)
    p.add_argument("--long", type=int, default=30)
    p.add_argument("--poll", type=float, default=0.3)
    args = p.parse_args()

    base = args.url or config.JETSON_BASE.rstrip("/")
    jetson_url = f"{base}/eeg"

    if not _REQUESTS_AVAILABLE:
        print("Error: pip install requests")
        sys.exit(1)

    run_live(
        jetson_url=jetson_url,
        mental_state=args.mental,
        warn_sec=args.warn,
        long_sec=args.long,
        poll_interval=args.poll,
    )


if __name__ == "__main__":
    main()
