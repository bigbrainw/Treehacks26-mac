#!/usr/bin/env python3
"""
Focus Block — Founders Inc productivity experiment.

Flow:
  1. Sit down. Enter today's goal.
  2. BASELINE (~60s): do nothing, we measure your resting EEG.
  3. WORK block (default 25 min): Do Not Disturb on, you work, we log EEG.
  4. Summary: focus pattern vs baseline — does focus decay over the block, when,
     or could this person sustain longer? Plus what apps were running.

We log every sample AND what's running on the machine (not just the foreground
window), so distractions sitting open in the background are visible too.

Usage:
  python focus_block.py                          # real Emotiv, 60s baseline, 25 min work
  python focus_block.py --goal "ship auth flow"
  python focus_block.py --baseline 60 --minutes 25
  python focus_block.py --mock                   # synthetic EEG, no headset
  python focus_block.py --no-dnd
  python focus_block.py --dnd-on "Start Focus" --dnd-off "Stop Focus"

Output:
  data/block_<ts>.csv           per-sample log (phase, EEG, activity, running_apps)
  data/block_<ts>_summary.txt   human-readable focus pattern + verdict
  data/block_<ts>_session.json  structured session data (baseline + work + verdict)
"""
import argparse
import json
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from activity import ActivityMonitor
from track import SessionLogger, _mock_loop

FOCUSED_THRESHOLD = 0.4  # focus >= this counts as "locked in" (matches parser)


# --- What's running (not just foreground) ---
def make_running_apps_fn():
    """Cached running-apps reader (refresh every 10s) + a set of everything seen."""
    seen = set()
    cache = {"apps": [], "t": 0.0}

    def fn():
        now = time.time()
        if now - cache["t"] > 10:
            apps = []
            if platform.system() == "Darwin":
                try:
                    from activity.macos import get_running_apps_macos
                    apps = get_running_apps_macos()
                except Exception:
                    apps = []
            cache["apps"] = apps
            cache["t"] = now
            seen.update(apps)
        return cache["apps"]

    return fn, seen


# --- Do Not Disturb (macOS Shortcuts, best-effort) ---
def _run_shortcut(name: str) -> bool:
    try:
        r = subprocess.run(["shortcuts", "run", name], capture_output=True, timeout=8)
        if r.returncode != 0:
            print(f"  [dnd] shortcut '{name}' failed: {r.stderr.decode().strip()[:80]}")
            return False
        return True
    except Exception as e:
        print(f"  [dnd] shortcut '{name}' error: {e}")
        return False


def dnd_on(name: str):
    print(f"  [dnd] ON via shortcut '{name}'")
    _run_shortcut(name)


def dnd_off(name: str):
    print(f"  [dnd] OFF via shortcut '{name}' (create this Shortcut to auto-disable)")
    _run_shortcut(name)


# --- Analysis helpers ---
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _slope_per_min(points):
    """Least-squares slope of focus vs minutes. points = [(minute_float, focus)]."""
    pts = [(m, f) for m, f in points if f is not None]
    n = len(pts)
    if n < 2:
        return None
    sx = sum(m for m, _ in pts)
    sy = sum(f for _, f in pts)
    sxx = sum(m * m for m, _ in pts)
    sxy = sum(m * f for m, f in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def _p(v):
    return "  -- " if v is None else f"{v:0.2f}"


def _bar(v):
    if v is None:
        return ""
    return "#" * max(0, min(10, round(v * 10)))


def analyze(goal, minutes, baseline_sec, samples, seen_apps, summary_path, json_path,
            source="emotiv", switches=None):
    lines = []
    def emit(s=""):
        lines.append(s)
        print(s)

    base = [s for s in samples if s[5] == "baseline"]
    work = [s for s in samples if s[5] == "work"]

    base_focus = _mean([s[3] for s in base])
    base_eng = _mean([s[1] for s in base])
    base_stress = _mean([s[2] for s in base])

    emit()
    emit("=" * 58)
    emit("  FOCUS BLOCK SUMMARY" + ("   *** MOCK DATA — NOT REAL EEG ***" if source == "mock" else ""))
    emit(f"  Source:   {source}")
    emit(f"  Goal:     {goal or '(none)'}")
    emit(f"  Baseline: {baseline_sec:g}s ({len(base)} samples)   "
         f"Work: {minutes:g} min ({len(work)} samples)")
    emit("=" * 58)
    emit(f"  BASELINE (resting):  focus {_p(base_focus)}  eng {_p(base_eng)}  stress {_p(base_stress)}")

    session = {
        "goal": goal,
        "source": source,
        "mock": source == "mock",
        "started": datetime.now().isoformat(timespec="seconds"),
        "baseline_sec": baseline_sec,
        "work_minutes": minutes,
        "baseline": {"focus": base_focus, "engagement": base_eng, "stress": base_stress,
                     "samples": len(base)},
        "running_apps_seen": sorted(seen_apps),
        "per_minute": [],
        "verdict": "",
    }

    if not work:
        emit("  No work-phase samples (headset signal? try --mock).")
        summary_path.write_text("\n".join(lines))
        json_path.write_text(json.dumps(session, indent=2))
        return

    t0 = work[0][0]
    rel = [((t - t0) / 60.0, eng, stress, foc) for (t, eng, stress, foc, _l, _ph) in work]
    labels = [s[4] for s in work]

    buckets = {}
    for m, eng, stress, foc in rel:
        buckets.setdefault(int(m), []).append((eng, stress, foc))

    emit()
    emit("  WORK, per minute (vs baseline focus):")
    emit("  min | focus  eng   stress | locked-in | vs base | trend")
    emit("  ----+---------------------+-----------+---------+-------------")
    prev = None
    for mi in sorted(buckets):
        rows = buckets[mi]
        mf = _mean([f for _, _, f in rows])
        me = _mean([e for e, _, _ in rows])
        mss = _mean([s for _, s, _ in rows])
        locked = sum(1 for _, _, f in rows if f is not None and f >= FOCUSED_THRESHOLD)
        pct = int(100 * locked / len(rows)) if rows else 0
        vs = "" if (mf is None or base_focus is None) else f"{mf - base_focus:+.2f}"
        arrow = ""
        if mf is not None and prev is not None:
            d = mf - prev
            arrow = "up" if d > 0.03 else ("down" if d < -0.03 else "flat")
        emit(f"  {mi:>3} | {_p(mf)}  {_p(me)}  {_p(mss)} |   {pct:>3}%    | {vs:>6}  | {arrow:<4} {_bar(mf)}")
        prev = mf if mf is not None else prev
        session["per_minute"].append({"minute": mi, "focus": mf, "engagement": me,
                                       "stress": mss, "locked_in_pct": pct})

    slope = _slope_per_min([(m, f) for m, _, _, f in rel])
    work_focus = _mean([f for _, _, _, f in rel])
    pct_focused = int(100 * sum(1 for l in labels if l == "focused") / len(labels))

    emit()
    emit(f"  Work focus avg: {_p(work_focus)}  (baseline {_p(base_focus)})   "
         f"time 'focused': {pct_focused}%")
    if slope is not None:
        emit(f"  Focus trend: {slope:+.3f} /min")

    # Decay: first work minute below baseline-derived floor (or absolute threshold)
    floor = FOCUSED_THRESHOLD if base_focus is None else min(FOCUSED_THRESHOLD, base_focus - 0.05)
    decay_min = None
    for mi in sorted(buckets):
        mf = _mean([f for _, _, f in buckets[mi]])
        if mf is not None and mf < floor:
            decay_min = mi
            break

    if slope is not None and slope < -0.015 and decay_min is not None:
        verdict = (f"Focus declined — dropped below {floor:.2f} around min {decay_min}. "
                   f"{minutes:g} min may be too long; break near ~{decay_min} min.")
    elif work_focus is not None and (base_focus is None or work_focus >= base_focus - 0.03) \
            and (slope is None or slope > -0.005):
        verdict = (f"Focus sustained the full {minutes:g} min (avg {work_focus:0.2f} vs "
                   f"baseline {_p(base_focus)}). Could try a LONGER block.")
    else:
        verdict = "Mixed pattern — no clean decay or sustain. Collect more blocks."

    session["verdict"] = verdict
    session["work"] = {"focus": work_focus, "slope_per_min": slope,
                       "pct_focused": pct_focused, "decay_minute": decay_min}

    # --- Tab/app switch ↔ EEG pattern ---
    switches = switches or []
    work_switches = [s for s in switches if s.get("phase") == "work"]
    session["switches"] = switches
    if work_switches:
        n = len(work_switches)
        per_min = n / minutes if minutes else 0
        # A switch is "unfocused" if the brain state at the switch wasn't 'focused'.
        unfocused = [s for s in work_switches if s.get("label") != "focused"]
        pct_unfocused = int(100 * len(unfocused) / n)
        sw_focus = _mean([s.get("focus") for s in work_switches])
        emit()
        emit("  TAB/APP SWITCHES (work phase):")
        emit(f"    {n} switches  ({per_min:.1f}/min)   "
             f"avg focus at switch {_p(sw_focus)} (session {_p(work_focus)})")
        emit(f"    {pct_unfocused}% happened while NOT focused "
             f"(distracted/drifting/stuck) — switching tracks disengagement.")
        # Show first few with timestamps + what the brain was doing.
        for s in work_switches[:6]:
            clk = s.get("iso", "")[11:19]
            emit(f"      {clk}  {s.get('label',''):<10} foc={_p(s.get('focus'))}  "
                 f"{(s.get('from') or '?')[:22]} -> {(s.get('to') or '?')[:22]}")
        session["switch_pattern"] = {
            "count": n, "per_min": per_min,
            "pct_while_unfocused": pct_unfocused,
            "avg_focus_at_switch": sw_focus,
        }

    emit()
    emit("  VERDICT:")
    emit(f"    {verdict}")
    if seen_apps:
        emit()
        emit(f"  Running during session ({len(seen_apps)}): {', '.join(sorted(seen_apps))}")
    emit("=" * 58)

    summary_path.write_text("\n".join(lines))
    json_path.write_text(json.dumps(session, indent=2))
    print(f"\n  Saved: {summary_path.name}, {json_path.name}")


def _sleep_phase(seconds, running):
    """Sleep in short slices so Ctrl+C is responsive. Returns False if interrupted."""
    end = time.time() + seconds
    while running[0] and time.time() < end:
        remaining = end - time.time()
        time.sleep(min(5.0, max(0.2, remaining)))
    return running[0]


def main():
    p = argparse.ArgumentParser(description="Baseline + timed focus block + EEG focus-pattern analysis.")
    p.add_argument("--goal", default=None, help="Today's goal. Prompts if omitted.")
    p.add_argument("--minutes", type=float, default=25.0, help="Work block length (default 25).")
    p.add_argument("--baseline", type=float, default=60.0, help="Baseline seconds doing nothing (default 60).")
    p.add_argument("--mock", action="store_true", help="Synthetic EEG (no headset).")
    p.add_argument("--profile", default=None, help="Emotiv BCI profile (default: config.EMOTIV_PROFILE).")
    p.add_argument("--poll", type=float, default=None, help="Sample interval sec (default: config.POLL_INTERVAL).")
    p.add_argument("--no-dnd", action="store_true", help="Don't toggle Do Not Disturb.")
    p.add_argument("--dnd-on", default="Start Focus", help="Shortcut name to enable DND.")
    p.add_argument("--dnd-off", default="Stop Focus", help="Shortcut name to disable DND.")
    p.add_argument("--autopilot", action="store_true",
                   help="Closed loop: drift -> auto-hide distraction; flow -> auto-DND.")
    p.add_argument("--no-flow-guard", action="store_true", help="Autopilot: skip auto-DND on flow.")
    p.add_argument("--focus-playlist", default=None,
                   help="Spotify URI for focus music on a recoverable dip.")
    args = p.parse_args()

    goal = args.goal
    if goal is None:
        try:
            goal = input("What are you shipping today? ").strip()
        except EOFError:
            goal = ""

    poll = args.poll if args.poll is not None else float(config.POLL_INTERVAL)
    source = "mock" if args.mock else "emotiv"
    suffix = "_MOCK" if args.mock else ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = config.DATA_DIR / f"block_{ts}{suffix}.csv"
    summary_path = config.DATA_DIR / f"block_{ts}{suffix}_summary.txt"
    json_path = config.DATA_DIR / f"block_{ts}{suffix}_session.json"

    activity = ActivityMonitor(poll_interval=poll)
    logger = SessionLogger(csv_path, activity)
    logger.source = source
    running_fn, seen_apps = make_running_apps_fn()
    logger.running_apps_fn = running_fn
    running = [True]

    # Closed-loop autopilot: EEG drift -> hide distraction; flow -> DND.
    pilot = None
    if args.autopilot:
        from autopilot import Autopilot
        pilot = Autopilot(goal=goal, enabled=True,
                          dnd_on_name=args.dnd_on, dnd_off_name=args.dnd_off,
                          flow_guard=not args.no_flow_guard,
                          focus_playlist=args.focus_playlist)
        # Only act during the work phase (set below when phase flips to "work").
        def _hook(now, ctx, ms):
            if logger.phase == "work":
                pilot.step(now, ctx, ms)
        logger.on_sample = _hook

    print("\n--- Focus Block ---")
    print(f"  Goal:     {goal or '(none)'}")
    print(f"  Baseline: {args.baseline:g}s   Work: {args.minutes:g} min   "
          f"EEG: {'mock' if args.mock else 'real Emotiv'}")
    print(f"  Logging:  {csv_path}")
    if pilot:
        print(f"  Autopilot: ON — drift hides distraction; "
              f"{'flow -> DND' if not args.no_flow_guard else 'no flow guard'}")
    print("  Ctrl+C to end early.\n")

    # Start EEG source (runs through both phases)
    client = None
    if args.mock:
        threading.Thread(target=_mock_loop, args=(logger, running, poll), daemon=True).start()
    else:
        if not config.EMOTIV_CLIENT_ID or not config.EMOTIV_CLIENT_SECRET:
            print("Error: real EEG needs EMOTIV_CLIENT_ID + EMOTIV_CLIENT_SECRET in .env")
            print("  Run: python check_emotiv_creds.py   (or: python focus_block.py --mock)")
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
        time.sleep(2)  # let session/profile/subscription settle before baseline

    try:
        # Phase 1: baseline
        logger.phase = "baseline"
        print(f"\n  >>> BASELINE: sit still, do nothing for {args.baseline:g}s...\n")
        _sleep_phase(args.baseline, running)

        # Phase 2: work (DND on)
        if running[0]:
            logger.phase = "work"
            print(f"\n  >>> WORK: {args.minutes:g} min. Go build: {goal or '(your goal)'}\n")
            # Autopilot manages DND dynamically (flow on / drift off); otherwise
            # turn DND on for the whole block.
            pilot_manages_dnd = pilot is not None and not args.no_flow_guard
            if not args.no_dnd and not pilot_manages_dnd:
                dnd_on(args.dnd_on)
            _sleep_phase(args.minutes * 60.0, running)
    except KeyboardInterrupt:
        print("\n  Ended early.")
    finally:
        running[0] = False
        if client:
            client.close()
        if pilot:
            pilot.shutdown()          # restore DND
        elif not args.no_dnd:
            dnd_off(args.dnd_off)
        time.sleep(0.3)  # flush last sample

    analyze(goal, args.minutes, args.baseline, list(logger.samples), seen_apps,
            summary_path, json_path, source=source, switches=list(logger.switches))
    logger.close()


if __name__ == "__main__":
    main()
