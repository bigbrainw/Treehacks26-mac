"""
Test: POST sample data to /eeg, show feedback from the response in window.
Feedback comes from the POST response body (e.g. {"feedback": "message"}).
"""
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from activity import ActivityMonitor
from feedback_window import FeedbackWindow
import requests


SAMPLE_STREAMS = {
    "met": {"met": [True, 0.65, True, 0.42, 0.38, True, 0.55, True, 0.72, True, 0.48, True, 0.58], "time": time.time()},
    "pow": {"pow": [2.1, 1.0, 0.25, 0.38, 0.23] * 14, "time": time.time()},
    "mot": {"mot": [11, 0, 0.64, -0.52, -0.46, -0.33, 0.94, -0.37, 0.04, -40.1, -4.1, -12.4], "time": time.time()},
    "dev": {"signal": 1.0, "dev": [4] * 14 + [100], "batteryPercent": 72, "time": time.time()},
}
SEND_INTERVAL = 2.0


def _send_and_show_feedback(eeg_url: str, window: FeedbackWindow):
    """POST to /eeg, parse response for feedback, update window."""
    activity = ActivityMonitor(poll_interval=1.0)
    count = 0
    while True:
        count += 1
        ctx = activity.get_current_activity()
        context = ctx.to_dict() if ctx else {}
        body = {"timestamp": time.time(), "streams": SAMPLE_STREAMS, "context": context}
        try:
            r = requests.post(
                eeg_url,
                json=body,
                headers={"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"},
                timeout=10,
            )
            print(f"[{count}] POST {eeg_url} -> {r.status_code}")
            if r.status_code == 200 and r.text:
                try:
                    data = r.json()
                    feedback = data.get("feedback") or data.get("message")
                    if feedback:
                        window.root.after(0, lambda t=feedback: window.update_feedback(t))
                        print(f"      feedback: {feedback[:60]}...")
                except ValueError:
                    pass
        except requests.RequestException as e:
            print(f"[{count}] POST failed: {e}")
        time.sleep(SEND_INTERVAL)


def main():
    load_dotenv(Path(__file__).parent / ".env")
    base = os.environ.get("JETSON_URL", "https://8061-68-65-164-46.ngrok-free.app").rstrip("/")
    eeg_url = f"{base}/eeg"

    print(f"POST {eeg_url} (feedback in response)")
    print("Close window to exit.\n")

    w = FeedbackWindow()  # No poll_url – feedback from POST response
    t = threading.Thread(target=_send_and_show_feedback, args=(eeg_url, w), daemon=True)
    t.start()
    w.run()


if __name__ == "__main__":
    main()
