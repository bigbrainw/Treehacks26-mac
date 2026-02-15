#!/usr/bin/env python3
"""
Test collector with mock EEG data (no Emotiv headset required).
Sends fake met + com over WebSocket; shows feedback in overlay if --show-feedback.
"""
import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import websocket
except ImportError:
    websocket = None

import config
from data_schema import CollectorPayload, EEGMetricsSnapshot, MentalStateSnapshot, ActivitySnapshot
from activity import ActivityMonitor

# Mock data (real format from Emotiv)
MOCK_MET = {"met": [True, 0.65, True, 0.42, 0.38, True, 0.55, True, 0.72, True, 0.48, True, 0.58], "time": 0}


def run_mock_collector(jetson_url: str, show_feedback: bool = False, interval: float = 2.0):
    if not websocket:
        print("Error: pip install websocket-client")
        sys.exit(1)

    ws_ref = {"ws": None}
    running = True

    def stop(_=None, __=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    activity = ActivityMonitor(poll_interval=interval)
    feedback_cb = None

    if show_feedback:
        from feedback_window import FeedbackWindow
        win = FeedbackWindow(width=360, height=160, use_poll=False)
        feedback_cb = win.update_feedback
        win.root.protocol("WM_DELETE_WINDOW", lambda: (stop(), win.root.destroy()))

    def send_payload(payload: CollectorPayload):
        if ws_ref["ws"] and ws_ref["ws"].sock and ws_ref["ws"].sock.connected:
            try:
                ws_ref["ws"].send(json.dumps(payload.to_dict()))
                print("  Sent:", payload.type)
            except Exception as e:
                print("  Send error:", e)

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "feedback" and feedback_cb:
                feedback_cb(data.get("feedback", ""))
                print("  Feedback:", data.get("feedback", "")[:50] + "...")
        except (json.JSONDecodeError, KeyError):
            pass

    def _make_activity_snapshot():
        ctx = activity.get_current_activity()
        if not ctx:
            return None
        return ActivitySnapshot(
            app_name=ctx.app_name,
            window_title=ctx.window_title,
            context_type=ctx.context_type,
            context_id=ctx.context_id,
            reading_section=ctx.reading_section,
        )

    def mock_sender():
        count = 0
        while running:
            count += 1
            t = time.time()
            act = _make_activity_snapshot()

            # 1. Activity/monitoring (dedicated payload so backend always gets it)
            if act:
                send_payload(CollectorPayload(type="activity", timestamp=t, activity=act))

            # 2. Mock EEG metrics + activity (processor uses both)
            met = dict(MOCK_MET)
            met["time"] = t
            send_payload(CollectorPayload(
                type="eeg",
                timestamp=t,
                eeg=EEGMetricsSnapshot(metrics=met),
                activity=act,
            ))

            # 3. Mock mental state (engagement, stress, etc. from met) - used for agent feedback
            met = dict(MOCK_MET)
            met["time"] = t
            send_payload(CollectorPayload(
                type="mental_state",
                timestamp=t,
                mental_state=MentalStateSnapshot(
                    engagement=0.55 + 0.15 * ((count % 5) / 5),
                    stress=0.35 + 0.2 * ((count % 7) / 7),
                    relaxation=0.4 + 0.2 * ((count % 3) / 3),
                    focus=0.5 + 0.2 * ((count % 11) / 11),
                    metrics=met,
                ),
            ))

            time.sleep(interval)

    ws = websocket.WebSocketApp(
        jetson_url,
        on_message=on_message if feedback_cb else None,
        on_open=lambda ws: print("  Connected to Jetson"),
        on_close=lambda ws, a, b: print("  Disconnected"),
        on_error=lambda ws, err: print("  WebSocket error:", err),
    )
    ws_ref["ws"] = ws

    print("Mock Collector starting...")
    print(f"  Target: {jetson_url}")
    print(f"  Sending mock EEG + mental_state + activity every {interval}s")
    if show_feedback:
        print("  Feedback window: open")
    print("  Ctrl+C or close window to stop\n")

    ws_thread = threading.Thread(target=lambda: ws.run_forever(), daemon=True)
    ws_thread.start()
    sender_thread = threading.Thread(target=mock_sender, daemon=True)
    sender_thread.start()

    time.sleep(2)

    if show_feedback:
        win.run()
    else:
        try:
            while running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            stop()

    print("\nStopped.")


def main():
    p = argparse.ArgumentParser(description="Mock EEG collector → Jetson WebSocket")
    p.add_argument("--url", default=config.JETSON_WS_URL, help="WebSocket URL")
    p.add_argument("--show-feedback", action="store_true", help="Show feedback overlay")
    p.add_argument("--interval", type=float, default=2.0, help="Send interval (seconds)")
    args = p.parse_args()
    run_mock_collector(args.url, show_feedback=args.show_feedback, interval=args.interval)


if __name__ == "__main__":
    main()
