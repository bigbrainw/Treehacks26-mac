"""
Send sample EEG + activity data to Jetson (no Emotiv headset required).
Use this to verify the Mac -> Jetson pipeline works.
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from activity import ActivityMonitor
import requests


# Sample data matching real Emotiv format
SAMPLE_MET = {"met": [True, 0.65, True, 0.42, 0.38, True, 0.55, True, 0.72, True, 0.48, True, 0.58], "time": time.time()}
SAMPLE_POW = {"pow": [2.1, 1.0, 0.25, 0.38, 0.23] * 14, "time": time.time()}  # 70 values for EPOC X
SAMPLE_MOT = {"mot": [11, 0, 0.64, -0.52, -0.46, -0.33, 0.94, -0.37, 0.04, -40.1, -4.1, -12.4], "time": time.time()}
SAMPLE_DEV = {"signal": 1.0, "dev": [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 100], "batteryPercent": 72, "time": time.time()}


def send_sample(jetson_url: str, count: int = 5):
    """Send count sample payloads to Jetson."""
    activity = ActivityMonitor(poll_interval=1.0)

    for i in range(count):
        ctx = activity.get_current_activity()
        context = ctx.to_dict() if ctx else {}

        body = {
            "timestamp": time.time(),
            "streams": {
                "met": SAMPLE_MET,
                "pow": SAMPLE_POW,
                "mot": SAMPLE_MOT,
                "dev": SAMPLE_DEV,
            },
            "context": context,
        }

        try:
            r = requests.post(
                jetson_url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "ngrok-skip-browser-warning": "1",
                },
                timeout=10,
            )
            print(f"[{i+1}/{count}] POST {jetson_url} -> {r.status_code}")
            if r.status_code != 200:
                print(f"         {r.text[:150]}")
        except requests.RequestException as e:
            print(f"[{i+1}/{count}] POST failed: {e}")

        if i < count - 1:
            time.sleep(2)


def main():
    load_dotenv(Path(__file__).parent / ".env")
    base = os.environ.get("JETSON_URL", "https://8061-68-65-164-46.ngrok-free.app").rstrip("/")
    jetson_url = f"{base}/eeg"

    print(f"Sending 5 sample payloads to {jetson_url}\n")
    send_sample(jetson_url, count=5)
    print("\nDone. Check Jetson logs to confirm receipt.")


if __name__ == "__main__":
    main()
