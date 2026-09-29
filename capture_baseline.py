#!/usr/bin/env python3
"""Capture and store a 60-second EMOTIV attention baseline."""

from __future__ import annotations

import json
import statistics
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from cortex import Cortex


CAPTURE_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 180.0
DATA_DIR = Path(__file__).resolve().parent / "data"


class BaselineCapture:
    def __init__(self) -> None:
        if not config.EMOTIV_CLIENT_ID or not config.EMOTIV_CLIENT_SECRET:
            raise RuntimeError("Missing EMOTIV_CLIENT_ID or EMOTIV_CLIENT_SECRET in .env")

        self.cortex = Cortex(
            config.EMOTIV_CLIENT_ID,
            config.EMOTIV_CLIENT_SECRET,
            debug_mode=False,
        )
        self.cortex.bind(create_session_done=self._on_session)
        self.cortex.bind(new_data_labels=self._on_labels)
        self.cortex.bind(new_met_data=self._on_met)
        self.cortex.bind(inform_error=self._on_error)

        self.columns: list[str] = []
        self.samples: list[dict] = []
        self.started_monotonic: float | None = None
        self.started_at: str | None = None
        self.done = threading.Event()
        self.failure: str | None = None
        self.output_path: Path | None = None
        self._finishing = False
        self.received_metric_count = 0

    def run(self) -> Path:
        thread = threading.Thread(target=self.cortex.open, daemon=True)
        thread.start()

        if not self.done.wait(CONNECT_TIMEOUT_SECONDS + CAPTURE_SECONDS):
            self.failure = "Timed out waiting for Cortex or valid attention samples."
            self._close()

        if self.failure:
            raise RuntimeError(self.failure)
        if self.output_path is None:
            raise RuntimeError("Baseline capture ended without writing an output file.")
        return self.output_path

    def _on_session(self, *args, **kwargs) -> None:
        print("Session ready. Subscribing to EMOTIV performance metrics...")
        self.cortex.sub_request(["met"])

    def _on_labels(self, *args, **kwargs) -> None:
        data = kwargs.get("data") or {}
        if data.get("streamName") == "met":
            self.columns = list(data.get("labels") or [])
            print("Waiting for the first valid attention sample...")

    def _on_met(self, *args, **kwargs) -> None:
        if self._finishing or not self.columns:
            return

        data = kwargs.get("data") or {}
        values = data.get("met") or []
        metrics = dict(zip(self.columns, values))
        attention = metrics.get("attention")
        active = metrics.get("attention.isActive")
        valid = active is True and isinstance(attention, (int, float))
        self.received_metric_count += 1

        if not valid and (
            self.received_metric_count == 1 or self.received_metric_count % 10 == 0
        ):
            print(
                "  metric received but attention unavailable"
                f" (isActive={active!r}, value={attention!r})"
            )

        now = time.monotonic()
        if valid and self.started_monotonic is None:
            self.started_monotonic = now
            self.started_at = datetime.now(timezone.utc).isoformat()
            print("Capturing 60 seconds. Stay focused on one normal work task...")

        if self.started_monotonic is None:
            return

        elapsed = now - self.started_monotonic
        self.samples.append(
            {
                "elapsedSeconds": round(elapsed, 3),
                "cortexTimestamp": data.get("time"),
                "attention": float(attention) if valid else None,
                "isActive": bool(active),
            }
        )

        remaining = max(0, int(CAPTURE_SECONDS - elapsed))
        if valid and (len(self.samples) == 1 or remaining % 10 == 0):
            print(f"  {remaining:02d}s remaining  attention={float(attention):.3f}")

        if elapsed >= CAPTURE_SECONDS:
            self._finish()

    def _on_error(self, *args, **kwargs) -> None:
        error = kwargs.get("error_data") or {}
        self.failure = f"Cortex error {error.get('code')}: {error.get('message', 'unknown error')}"
        self._close()

    def _finish(self) -> None:
        if self._finishing:
            return
        self._finishing = True

        valid_values = [
            sample["attention"]
            for sample in self.samples
            if sample["isActive"] and sample["attention"] is not None
        ]
        if len(valid_values) < 3:
            self.failure = f"Only {len(valid_values)} valid samples arrived in 60 seconds."
            self._close()
            return

        sorted_values = sorted(valid_values)
        payload = {
            "schemaVersion": 1,
            "kind": "emotivAttentionBaseline",
            "durationSeconds": 60,
            "startedAt": self.started_at,
            "endedAt": datetime.now(timezone.utc).isoformat(),
            "baseline": {
                "attentionMedian": statistics.median(valid_values),
                "attentionMean": statistics.fmean(valid_values),
                "attentionStdDev": (
                    statistics.pstdev(valid_values) if len(valid_values) > 1 else 0.0
                ),
                "attentionMin": min(valid_values),
                "attentionMax": max(valid_values),
                "validSampleCount": len(valid_values),
                "totalSampleCount": len(self.samples),
                "validCoverage": len(valid_values) / len(self.samples),
            },
            "samples": self.samples,
        }

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = DATA_DIR / f"emotiv_baseline_1min_{stamp}.json"
        latest_path = DATA_DIR / "emotiv_baseline_1min_latest.json"
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.output_path.write_text(encoded)
        latest_path.write_text(encoded)

        baseline = payload["baseline"]
        print(
            "Baseline stored:"
            f" median={baseline['attentionMedian']:.3f},"
            f" mean={baseline['attentionMean']:.3f},"
            f" valid={baseline['validSampleCount']}/{baseline['totalSampleCount']}"
        )
        print(f"  {self.output_path}")
        print(f"  {latest_path}")
        self._close()

    def _close(self) -> None:
        try:
            if self.cortex.session_id:
                self.cortex.unsub_request(["met"])
        except Exception:
            pass
        # Closing the WebSocket automatically closes its Cortex session. Avoid calling
        # the vendored close_session(): it reuses CREATE_SESSION_ID, so its response is
        # incorrectly dispatched as another createSession result and resubscribes.
        threading.Timer(0.5, self.cortex.close).start()
        self.done.set()


def main() -> None:
    capture = BaselineCapture()
    try:
        capture.run()
    except KeyboardInterrupt:
        print("\nCapture cancelled; no baseline was stored.")
        capture._close()


if __name__ == "__main__":
    main()
