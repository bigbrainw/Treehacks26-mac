#!/usr/bin/env python3
"""
Focus Tracker — connect to Emotiv EEG + read what's on the computer, and log a
timestamped row of activity + mental state so you can review WHEN you locked in
and when you didn't.

Each row = one `met` sample (real headset) or one mock tick. The `label` column
is the lock-in signal: "focused" = locked in; "stuck"/"confused"/"distracted" = not.

Usage:
  python track.py                     # real Emotiv headset (default)
  python track.py --mock              # synthetic met stream, no headset
  python track.py --profile Elijah    # Emotiv BCI profile (default: config.EMOTIV_PROFILE)
  python track.py --out my.csv        # override CSV path
  python track.py --poll 1.0          # mock/activity sample interval (sec)

Output: data/session_YYYYMMDD_HHMMSS.csv  (+ live console line per sample)
"""
import argparse
import csv
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from activity import ActivityMonitor
from mental_state_parser import derive_mental_state_label, parse_met_to_mental_state

CSV_COLUMNS = [
    "timestamp", "iso_time", "source", "phase",
    "app", "window", "context_type", "context_id", "section",
    "engagement", "stress", "focus", "relaxation", "excitement", "interest",
    "label", "switched", "switch_from", "running_apps",
]


def _fmt(v):
    """Metric -> string; blank when None (poor signal)."""
    return "" if v is None else f"{v:.3f}"


class SessionLogger:
    """Writes one timestamped row per sample. Thread-safe (met callbacks fire on
    the Cortex thread; mock runs on its own thread)."""

    def __init__(self, out_path: Path, activity: ActivityMonitor):
        self.activity = activity
        self.out_path = out_path
        self._lock = threading.Lock()
        self._rows = 0
        self.samples = []  # (timestamp, engagement, stress, focus, label, phase) for analysis
        self.switches = []  # switch events: dicts with t, from_*, to_*, eeg at switch
        self._last_cid = None      # previous context_id, to detect tab/app switches
        self._last_ctx_disp = ""   # previous context display (app | window)
        self.phase = ""            # set by caller: "baseline" | "work" | ""
        self.source = ""           # set by caller: "mock" | "emotiv"
        self.running_apps_fn = None  # optional callable -> list[str] of running apps
        self.on_sample = None      # optional hook(now, ctx, ms) after each logged sample
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(out_path, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(CSV_COLUMNS)
        self._fh.flush()

    def log(self, metrics: dict):
        """Sample activity + parse metrics, append a row, print a live line."""
        try:
            now = time.time()
            ctx = self.activity.get_current_activity()
            ms = parse_met_to_mental_state(metrics)
            label = derive_mental_state_label(ms)

            app = getattr(ctx, "app_name", "") or ""
            window = getattr(ctx, "window_title", "") or ""
            ctype = getattr(ctx, "context_type", "") or ""
            cid = getattr(ctx, "context_id", "") or ""
            section = getattr(ctx, "reading_section", "") or ""
            running = ""
            if self.running_apps_fn:
                try:
                    running = ", ".join(self.running_apps_fn())
                except Exception:
                    running = ""

            # Detect a tab/app switch: context_id changed since the last sample.
            disp = f"{app} | {window}".strip(" |")
            switched = self._last_cid is not None and cid != self._last_cid
            switch_from = self._last_ctx_disp if switched else ""
            if switched:
                self.switches.append({
                    "t": now,
                    "iso": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
                    "phase": self.phase,
                    "from": self._last_ctx_disp, "to": disp,
                    "engagement": ms.engagement, "stress": ms.stress,
                    "focus": ms.focus, "label": label,
                })
            self._last_cid = cid
            self._last_ctx_disp = disp

            row = [
                f"{now:.3f}",
                datetime.fromtimestamp(now).isoformat(timespec="seconds"),
                self.source, self.phase,
                app, window, ctype, cid, section,
                _fmt(ms.engagement), _fmt(ms.stress), _fmt(ms.focus),
                _fmt(ms.relaxation), _fmt(ms.excitement), _fmt(ms.interest),
                label, "1" if switched else "0", switch_from, running,
            ]
            with self._lock:
                self._writer.writerow(row)
                self._fh.flush()
                self._rows += 1
                self.samples.append((now, ms.engagement, ms.stress, ms.focus, label, self.phase))

            clock = datetime.fromtimestamp(now).strftime("%H:%M:%S")
            win_short = window[:35] + ("…" if len(window) > 35 else "")
            tag = f"[{self.phase}] " if self.phase else ""
            sw = " ⇄SWITCH" if switched else ""
            print(
                f"{clock} {tag}{label:<10} "
                f"eng={_fmt(ms.engagement) or '  - '} "
                f"str={_fmt(ms.stress) or '  - '} "
                f"foc={_fmt(ms.focus) or '  - '}  "
                f"{app or '?'} | {win_short}{sw}"
            )
            if self.on_sample:
                try:
                    self.on_sample(now, ctx, ms)
                except Exception as e:
                    print(f"  [autopilot] error: {e}")
        except Exception as e:
            print(f"  [warn] log skipped: {e}")

    def close(self):
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass
        print(f"\nStopped. {self._rows} rows -> {self.out_path}")


def _mock_loop(logger: SessionLogger, running_ref: list, poll: float):
    """Synthetic met stream so you can test without a headset. Metrics vary so the
    derived label flips between focused / stuck / distracted over time."""
    c = 0
    while running_ref[0]:
        c += 1
        t = time.time()
        # Order matches EPOC/Insight/Flex cols in mental_state_parser fallback.
        metrics = {
            "met": [
                True, 0.55 + 0.20 * ((c % 5) / 5),   # eng.isActive, eng
                True, 0.40, 0.35,                     # exc.isActive, exc, lex
                True, 0.30 + 0.30 * ((c % 7) / 7),    # str.isActive, str
                True, 0.40 + 0.20 * ((c % 3) / 3),    # rel.isActive, rel
                True, 0.45,                           # int.isActive, int
                True, 0.35 + 0.30 * ((c % 11) / 11),  # attention.isActive, attention
            ],
            "time": t,
        }
        logger.log(metrics)
        time.sleep(poll)


def main():
    p = argparse.ArgumentParser(description="Log timestamped activity + EEG mental state to CSV.")
    p.add_argument("--mock", action="store_true", help="Synthetic met stream (no headset).")
    p.add_argument("--profile", default=None, help="Emotiv BCI profile (default: config.EMOTIV_PROFILE).")
    p.add_argument("--out", default=None, help="CSV output path (default: data/session_<ts>.csv).")
    p.add_argument("--poll", type=float, default=None, help="Mock/activity sample interval sec (default: config.POLL_INTERVAL).")
    args = p.parse_args()

    poll = args.poll if args.poll is not None else float(config.POLL_INTERVAL)
    source = "mock" if args.mock else "emotiv"
    suffix = "_MOCK" if args.mock else ""
    out_path = Path(args.out) if args.out else (
        config.DATA_DIR / f"session_{datetime.now():%Y%m%d_%H%M%S}{suffix}.csv"
    )

    activity = ActivityMonitor(poll_interval=poll)
    logger = SessionLogger(out_path, activity)
    logger.source = source
    running = [True]

    def stop(_=None, __=None):
        running[0] = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print("--- Focus Tracker ---")
    print(f"  EEG:      {'mock' if args.mock else 'real Emotiv'}")
    print(f"  Activity: real (app, window, context)")
    print(f"  Logging:  {out_path}")
    print("  label 'focused' = locked in; stuck/confused/distracted = not.")
    print("  Ctrl+C to stop.\n")

    if args.mock:
        _mock_loop(logger, running, poll)
    else:
        if not config.EMOTIV_CLIENT_ID or not config.EMOTIV_CLIENT_SECRET:
            print("Error: real EEG needs EMOTIV_CLIENT_ID + EMOTIV_CLIENT_SECRET in .env")
            print("  Run: python check_emotiv_creds.py   (or: python track.py --mock)")
            logger.close()
            sys.exit(1)
        from eeg import EmotivCortexClient

        profile = args.profile or getattr(config, "EMOTIV_PROFILE", "Elijah")
        client = EmotivCortexClient(
            client_id=config.EMOTIV_CLIENT_ID,
            client_secret=config.EMOTIV_CLIENT_SECRET,
            on_metrics=logger.log,
            streams=["met"],
            profile_name=profile,
        )
        client.connect()
        print(f"  Emotiv Cortex: connecting... (met, profile={profile})")
        try:
            while running[0]:
                time.sleep(0.5)
        finally:
            client.close()

    logger.close()


if __name__ == "__main__":
    main()
