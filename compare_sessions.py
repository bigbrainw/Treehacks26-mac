#!/usr/bin/env python3
"""
Compare two (or more) focus-session CSVs to see how the brain + behavior differ
across tasks — e.g. deep work vs doom scrolling.

Usage:
  python compare_sessions.py data/block_A.csv data/block_B.csv
  python compare_sessions.py               # auto: two newest block_*.csv
"""
import csv
import glob
import json
import sys
from collections import Counter
from pathlib import Path

import config


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(path: Path) -> dict:
    rows = list(csv.DictReader(open(path, newline="")))
    work = [r for r in rows if r.get("phase") in ("work", "", None)] or rows
    def col(name):
        return [_f(r.get(name)) for r in work if _f(r.get(name)) is not None]
    eng, foc, str_ = col("engagement"), col("focus"), col("stress")
    labels = [r.get("label", "") for r in work]
    switches = sum(1 for r in work if r.get("switched") == "1")
    has_switch_col = any("switched" in r and r.get("switched") not in (None, "") for r in work)
    # Duration from timestamps
    ts = [_f(r.get("timestamp")) for r in work if _f(r.get("timestamp"))]
    dur_min = (max(ts) - min(ts)) / 60 if len(ts) >= 2 else 0
    # Apps / pages viewed
    apps = Counter(r.get("app", "") for r in work if r.get("app"))
    pages = Counter((r.get("window") or r.get("section") or "").strip()
                    for r in work if (r.get("window") or r.get("section")))
    # Goal from sibling json
    goal, source = "", (work[0].get("source", "") if work else "")
    jp = path.with_name(path.stem + "_session.json")
    if jp.exists():
        try:
            j = json.load(open(jp))
            goal = j.get("goal", "")
        except Exception:
            pass

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    n = len(work)
    lc = Counter(labels)
    return {
        "name": path.name, "goal": goal, "source": source,
        "samples": n, "dur_min": dur_min,
        "engagement": mean(eng), "focus": mean(foc), "stress": mean(str_),
        "pct_focused": 100 * lc.get("focused", 0) / n if n else 0,
        "pct_distracted": 100 * (lc.get("distracted", 0) + lc.get("drifting", 0)) / n if n else 0,
        "pct_confused": 100 * (lc.get("confused", 0) + lc.get("stuck", 0)) / n if n else 0,
        "switches": switches, "has_switch_col": has_switch_col,
        "switch_per_min": switches / dur_min if dur_min else 0,
        "top_apps": apps.most_common(4),
        "top_pages": pages.most_common(4),
    }


def _p(v, pct=False):
    if v is None:
        return "  --"
    return f"{v:5.0f}%" if pct else f"{v:5.2f}"


def row(label, a, b, key, pct=False):
    return f"  {label:<20} | {_p(a.get(key), pct):>8} | {_p(b.get(key), pct):>8}"


def main():
    args = sys.argv[1:]
    if len(args) >= 2:
        paths = [Path(a) for a in args[:2]]
    else:
        found = sorted(glob.glob(str(config.DATA_DIR / "block_*.csv")),
                       key=lambda p: Path(p).stat().st_mtime, reverse=True)
        # skip _MOCK unless nothing else
        real = [p for p in found if "_MOCK" not in p] or found
        if len(real) < 2:
            print("Need two block_*.csv files. Pass paths explicitly.")
            sys.exit(1)
        paths = [Path(real[0]), Path(real[1])]

    a, b = load(paths[0]), load(paths[1])

    print("=" * 60)
    print("  SESSION COMPARISON")
    print(f"  A: {a['goal'] or a['name']}  ({a['source']}, {a['dur_min']:.0f} min, {a['samples']} samples)")
    print(f"  B: {b['goal'] or b['name']}  ({b['source']}, {b['dur_min']:.0f} min, {b['samples']} samples)")
    print("=" * 60)
    print(f"  {'metric':<20} | {'A':>8} | {'B':>8}")
    print("  " + "-" * 42)
    print(row("engagement (avg)", a, b, "engagement"))
    print(row("focus (avg)", a, b, "focus"))
    print(row("stress (avg)", a, b, "stress"))
    print(row("% focused", a, b, "pct_focused", pct=True))
    print(row("% distracted/drift", a, b, "pct_distracted", pct=True))
    print(row("% confused/stuck", a, b, "pct_confused", pct=True))
    print(row("tab switches", a, b, "switches"))
    print(row("switches / min", a, b, "switch_per_min"))

    for tag, s in (("A", a), ("B", b)):
        print()
        print(f"  {tag} — {s['goal'] or s['name']}")
        print(f"     apps:  " + ", ".join(f"{k}({v})" for k, v in s["top_apps"]))
        pages = ", ".join(f"{(k[:34] or '—')}" for k, _ in s["top_pages"] if k)
        if pages:
            print(f"     pages: {pages}")

    # Verdict
    print()
    print("  DIFFERENCE:")
    de = (b['engagement'] or 0) - (a['engagement'] or 0)
    df = (b['focus'] or 0) - (a['focus'] or 0)
    dsw = b['switch_per_min'] - a['switch_per_min']
    parts = []
    if abs(df) >= 0.03:
        parts.append(f"focus {'lower' if df < 0 else 'higher'} in B by {abs(df):.2f}")
    if abs(de) >= 0.03:
        parts.append(f"engagement {'lower' if de < 0 else 'higher'} in B by {abs(de):.2f}")
    if b['has_switch_col'] and a['has_switch_col'] and abs(dsw) >= 0.2:
        parts.append(f"{'more' if dsw > 0 else 'fewer'} tab switches/min in B ({dsw:+.1f})")
    elif b['has_switch_col'] and not a['has_switch_col']:
        parts.append(f"B switched tabs {b['switch_per_min']:.1f}/min (A predates switch tracking)")
    print("    " + ("; ".join(parts) if parts else "sessions look similar."))
    print("    Hypothesis: doom-scrolling = lower sustained focus + more context switching")
    print("    than deep work, even if raw engagement looks active.")
    print("=" * 60)


if __name__ == "__main__":
    main()
