#!/usr/bin/env python3
"""
Generate a realistic MOCK focus-block session (CSV + session.json) in the
Python tracker's exact format, so the NeuroFocus Mac app can display a believable
demo instead of the hardcoded DayMock day.

Synthesizes ~40 min ending "now": short baseline, then a work block with a real
arc — warm-up, deep-focus peak, a mid-block dip with tab switches to
distractions, recovery, then late fatigue decline. Engagement runs through the
same label/stage logic as live data, so nothing here is hand-placed.

Usage:
  python mock_session.py                 # 40 min work, writes to data/
  python mock_session.py --minutes 50 --goal "ship the demo"
"""
import argparse
import csv
import json
import math
import random
from datetime import datetime
from pathlib import Path

import config
from data_schema import MentalStateSnapshot
from mental_state_parser import derive_mental_state_label
from track import CSV_COLUMNS

# Believable app timeline: (app, window, context_type, context_id, is_distraction)
WORK_CTXS = [
    ("Code", "focus_block.py — Treehacks26", "file", "Code::focus_block.py", False),
    ("Brave Browser", "Emotiv Cortex API docs", "website", "Brave::emotiv.gitbook.io", False),
    ("iTerm2", "swift build", "terminal", "iTerm2::", False),
]
DISTRACTIONS = [
    ("Slack", "#general", "app", "Slack::general", True),
    ("Brave Browser", "X — Home", "website", "Brave::x.com", True),
    ("Messages", "Mom", "app", "Messages::mom", True),
]
RUNNING = ["Code", "Brave Browser", "iTerm2", "Slack", "Spotify", "Messages",
           "EMOTIV Launcher", "Finder", "Notes", "Discord"]


def engagement_curve(frac: float) -> float:
    """Engagement over the work block, frac in [0,1]. Real focus-block arc."""
    warmup = 0.55 + 0.30 * min(1.0, frac / 0.12)                 # ramp up first ~12%
    peak = 0.30 * math.exp(-((frac - 0.30) ** 2) / (2 * 0.10 ** 2))  # deep peak ~30%
    dip = -0.35 * math.exp(-((frac - 0.55) ** 2) / (2 * 0.06 ** 2))  # mid dip ~55%
    recover = 0.18 * math.exp(-((frac - 0.72) ** 2) / (2 * 0.08 ** 2))
    fatigue = -0.28 * max(0.0, frac - 0.80) / 0.20              # decline after 80%
    return max(0.08, min(0.95, warmup + peak + dip + recover + fatigue))


def main():
    p = argparse.ArgumentParser(description="Generate a realistic mock focus session.")
    p.add_argument("--minutes", type=float, default=40.0)
    p.add_argument("--baseline", type=float, default=60.0)
    p.add_argument("--goal", default="ship the NeuroFocus demo")
    p.add_argument("--step", type=float, default=2.0, help="seconds between samples")
    args = p.parse_args()

    random.seed(7)
    step = args.step
    n_base = int(args.baseline / step)
    n_work = int(args.minutes * 60 / step)
    total = n_base + n_work
    start = datetime.now().timestamp() - total * step  # session ends ~now

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = config.DATA_DIR / f"block_{ts}_MOCK.csv"
    json_path = config.DATA_DIR / f"block_{ts}_MOCK_session.json"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    samples = []          # (t, eng, stress, focus, label, phase)
    switches = []
    seen = set()
    last_cid = None
    last_disp = ""
    cur = WORK_CTXS[0]
    dwell = 0

    for i in range(total):
        t = start + i * step
        phase = "baseline" if i < n_base else "work"
        if phase == "baseline":
            eng = 0.48 + random.uniform(-0.05, 0.05)
            ctx = ("iTerm2", "", "terminal", "iTerm2::", False)
        else:
            frac = (i - n_base) / max(1, n_work)
            eng = engagement_curve(frac) + random.uniform(-0.04, 0.04)
            eng = max(0.05, min(0.97, eng))
            # Pick context: during the dip, drift to distractions; else work apps.
            dwell -= 1
            if dwell <= 0:
                if eng < 0.40 and random.random() < 0.6:
                    cur = random.choice(DISTRACTIONS)
                    dwell = random.randint(2, 5)      # short distraction bursts
                else:
                    cur = random.choice(WORK_CTXS)
                    dwell = random.randint(6, 14)     # longer work dwell
            ctx = cur

        # Stress inversely tracks engagement; focus tracks engagement.
        stress = max(0.05, min(0.95, 0.75 - 0.5 * eng + random.uniform(-0.05, 0.05)))
        focus = max(0.05, min(0.95, 0.15 + 0.65 * eng + random.uniform(-0.04, 0.04)))
        excitement, interest, relaxation = 0.40, 0.45, max(0.1, 0.8 - stress)

        ms = MentalStateSnapshot(engagement=eng, stress=stress, relaxation=relaxation,
                                 focus=focus, excitement=excitement, interest=interest,
                                 metrics={})
        label = derive_mental_state_label(ms)

        app, window, ctype, cid, _dist = ctx
        disp = f"{app} | {window}".strip(" |")
        switched = last_cid is not None and cid != last_cid
        switch_from = last_disp if switched else ""
        if switched:
            switches.append({"t": t, "iso": datetime.fromtimestamp(t).isoformat(timespec="seconds"),
                             "phase": phase, "from": last_disp, "to": disp,
                             "engagement": eng, "stress": stress, "focus": focus, "label": label})
        last_cid, last_disp = cid, disp

        running = random.sample(RUNNING, k=random.randint(7, len(RUNNING)))
        seen.update(running)

        def f(v):
            return f"{v:.3f}"
        rows.append([
            f"{t:.3f}", datetime.fromtimestamp(t).isoformat(timespec="seconds"),
            "mock", phase, app, window, ctype, cid, "",
            f(eng), f(stress), f(focus), f(relaxation), f(excitement), f(interest),
            label, "1" if switched else "0", switch_from, ", ".join(running),
        ])
        samples.append((t, eng, stress, focus, label, phase))

    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        w.writerows(rows)

    work = [s for s in samples if s[5] == "work"]
    work_switches = [s for s in switches if s["phase"] == "work"]
    unfocused = [s for s in work_switches if s["label"] != "focused"]
    avg_focus = sum(s[3] for s in work) / len(work) if work else 0
    session = {
        "goal": args.goal, "source": "mock", "mock": True,
        "started": datetime.fromtimestamp(start).isoformat(timespec="seconds"),
        "baseline_sec": args.baseline, "work_minutes": args.minutes,
        "switch_pattern": {
            "count": len(work_switches),
            "pct_while_unfocused": int(100 * len(unfocused) / len(work_switches)) if work_switches else 0,
        },
        "verdict": "Mock demo session.",
    }
    json_path.write_text(json.dumps(session, indent=2))

    print(f"Wrote {len(rows)} rows -> {csv_path}")
    print(f"  work switches: {len(work_switches)}  avg work focus: {avg_focus:.2f}")
    print(f"  session json  -> {json_path}")
    print("  NeuroFocus app polls every 3s — it will pick this up if open.")


if __name__ == "__main__":
    main()
