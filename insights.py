#!/usr/bin/env python3
"""
Feed a full focus session (EEG + computer activity timeline) to GPT and get back
where the user's attention went, the specific patterns linking activity to focus,
and concrete, personalized ways to be more productive.

We already track everything — apps, window titles, URLs, tab switches, and the
per-sample Emotiv focus/engagement/stress. This compresses it into a per-minute
timeline GPT can reason over, then asks GPT-5.6 for evidence-based advice.

Usage:
  python insights.py                       # newest real session
  python insights.py data/block_X.csv
"""
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import config

load_dotenv(config.DATA_DIR.parent / ".env")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6")
API_KEY = os.environ.get("OPEN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_timeline(path: Path) -> dict:
    rows = list(csv.DictReader(open(path, newline="")))
    goal, source = "", (rows[0].get("source", "") if rows else "")
    jp = path.with_name(path.stem + "_session.json")
    if jp.exists():
        try:
            goal = json.load(open(jp)).get("goal", "")
        except Exception:
            pass

    per_min = defaultdict(lambda: {"foc": [], "eng": [], "str": [],
                                   "apps": Counter(), "pages": Counter(),
                                   "labels": Counter(), "switches": 0})
    t0 = _f(rows[0]["timestamp"]) if rows else 0
    switches_detail = []
    for r in rows:
        if r.get("phase") == "baseline":
            continue
        t = _f(r.get("timestamp")) or t0
        m = int((t - t0) / 60)
        b = per_min[m]
        for k, col in (("foc", "focus"), ("eng", "engagement"), ("str", "stress")):
            v = _f(r.get(col))
            if v is not None:
                b[k].append(v)
        app = r.get("app", "") or "?"
        page = (r.get("window") or r.get("section") or "").strip()
        b["apps"][app] += 1
        if page:
            b["pages"][page[:60]] += 1
        b["labels"][r.get("label", "")] += 1
        if r.get("switched") == "1":
            b["switches"] += 1
            switches_detail.append({
                "min": m, "to": (r.get("app", "") + " | " + (r.get("window") or r.get("section") or ""))[:60],
                "focus": _f(r.get("focus")),
            })

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    timeline = []
    for m in sorted(per_min):
        b = per_min[m]
        timeline.append({
            "min": m,
            "focus": avg(b["foc"]), "engagement": avg(b["eng"]), "stress": avg(b["str"]),
            "app": b["apps"].most_common(1)[0][0] if b["apps"] else "?",
            "page": b["pages"].most_common(1)[0][0] if b["pages"] else "",
            "state": b["labels"].most_common(1)[0][0] if b["labels"] else "",
            "switches": b["switches"],
        })

    return {
        "goal": goal, "source": source, "file": path.name,
        "duration_min": len(timeline),
        "timeline": timeline,
        "switch_events": switches_detail[:40],
    }


PROMPT = """You are a focus/productivity analyst. You are given ONE work session:
the user's stated goal, plus a per-minute timeline combining EEG focus signals
(focus = sustained attention 0-1, engagement = brain activation 0-1, stress 0-1;
state = classifier label) with computer activity (foreground app, page/URL, and
number of tab/app switches that minute).

Key idea: engagement can be high while focus is low — that is distraction
(e.g. doom-scrolling feels engaging but attention is scattered). Judge real
productivity by FOCUS + whether the activity matched the goal.

Analyze THIS session and answer concretely, citing minute numbers, apps/pages,
and focus values from the data (no generic advice):

1. WHERE the attention actually went (which apps/pages held focus, which drained it).
2. The single clearest PATTERN linking their activity to their focus
   (e.g. "focus dropped from 0.6 to 0.35 within 2 min every time X opened").
3. 2-3 SPECIFIC, personalized changes to be more productive next session,
   each tied to evidence from this data.

Be direct and brief. Use the user's real numbers."""


def main():
    if not API_KEY:
        print("Missing OPEN_AI_API_KEY in .env")
        sys.exit(1)
    args = [a for a in sys.argv[1:]]
    if args:
        path = Path(args[0])
    else:
        found = sorted(glob.glob(str(config.DATA_DIR / "block_*.csv")),
                       key=lambda p: Path(p).stat().st_mtime, reverse=True)
        real = [p for p in found if "_MOCK" not in p] or found
        if not real:
            print("No session CSV found.")
            sys.exit(1)
        path = Path(real[0])

    data = build_timeline(path)
    print(f"Session: {data['file']}  goal={data['goal']!r}  {data['duration_min']} min, "
          f"{len(data['switch_events'])} switches")
    print("Asking GPT-5.6 to find the pattern...\n")

    from openai import OpenAI
    client = OpenAI(api_key=API_KEY)
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps(data)},
        ],
    )
    out = r.choices[0].message.content
    print(out)

    # Save alongside the session for the app / record.
    out_path = path.with_name(path.stem + "_insights.txt")
    out_path.write_text(f"Goal: {data['goal']}\n\n{out}\n")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
