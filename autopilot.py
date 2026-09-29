#!/usr/bin/env python3
"""
Focus Autopilot — closed loop, no text to read.

EEG is the trigger, the Mac is the actuator:
  * DRIFT  (attention drops + you're on a distraction off your goal) -> hide that
           window and bring your work app back. The temptation just disappears.
  * FLOW   (sustained focus) -> Do Not Disturb on, notifications silenced.
  * OUT OF FLOW -> DND off.

Everything is reversible (hide, not close) and rate-limited. Plugged into
focus_block via a per-sample hook; also usable standalone.
"""
import re
import subprocess
import time

# Pages/apps that count as distractions when you're off-goal.
DISTRACTION_HINTS = [
    "x.com", "twitter", "/reels", "instagram", "youtube.com/shorts", "/shorts",
    "tiktok", "reddit", "facebook", "netflix", "twitch", "discord",
]
# Never auto-hide these even if attention dips (system / your own tools).
NEVER_HIDE = {"finder", "system events", "python", "terminal", "iterm2", "loginwindow"}


def _osa(script: str, timeout: float = 2.0) -> bool:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


class Autopilot:
    DRIFT_FOCUS = 0.40        # attention below this = slipping
    FLOW_FOCUS = 0.47         # at/above this sustained = locked in
    DRIFT_HOLD_SEC = 6.0      # must be drifting + on distraction this long before acting
    FLOW_HOLD_SEC = 25.0      # sustained focus before protecting flow
    ACTION_COOLDOWN = 15.0    # min seconds between hide actions

    # Spotify "Deep Focus" playlist (instrumental / brain-focus). Overridable.
    FOCUS_PLAYLIST = "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ"

    def __init__(self, goal: str = "", enabled: bool = True,
                 dnd_on_name: str = "Start Focus", dnd_off_name: str = "Stop Focus",
                 flow_guard: bool = True, focus_playlist: str | None = None):
        self.enabled = enabled
        self.flow_guard = flow_guard
        self.focus_playlist = focus_playlist or self.FOCUS_PLAYLIST
        self.goal_kw = [w.lower() for w in re.findall(r"\w+", goal) if len(w) > 3]
        self.dnd_on_name = dnd_on_name
        self.dnd_off_name = dnd_off_name

        self.last_on_task_app = None
        self._drift_since = None
        self._flow_since = None
        self._last_action = 0.0
        self._dnd = False
        self._peak_focus = 0.0     # best focus this session, for dip depth
        self._last_nudge = 0.0
        self._session_start = time.time()

    # --- classification ---
    def _text(self, ctx) -> str:
        t = " ".join(str(getattr(ctx, a, "") or "") for a in
                     ("app_name", "window_title", "context_id", "reading_section"))
        return t.lower()

    def _is_distraction(self, ctx) -> bool:
        return any(h in self._text(ctx) for h in DISTRACTION_HINTS)

    def _on_goal(self, ctx) -> bool:
        if not self.goal_kw:
            return False
        t = self._text(ctx)
        return any(k in t for k in self.goal_kw)

    def _is_work_app(self, ctx) -> bool:
        app = (getattr(ctx, "app_name", "") or "").lower()
        return any(w in app for w in ("code", "cursor", "xcode", "iterm", "terminal",
                                      "vim", "sublime", "word", "pages", "notion"))

    # --- actions ---
    def _hide_front_and_return(self, ctx):
        app = (getattr(ctx, "app_name", "") or "").strip()
        if app.lower() in NEVER_HIDE:
            return
        # Hide the distraction app (reversible).
        _osa(f'tell application "System Events" to set visible of '
             f'(first process whose frontmost is true) to false')
        # Bring the last real work app forward.
        target = self.last_on_task_app
        if target and target.lower() not in NEVER_HIDE:
            _osa(f'tell application "{target}" to activate')
        print(f"  [autopilot] DRIFT -> hid {app or '?'}"
              + (f", back to {target}" if target else ""))

    def _notify(self, title: str, body: str):
        _osa(f'display notification "{body}" with title "{title}" sound name "Glass"')

    def _play_focus_music(self) -> bool:
        """Switch Spotify to brain-focus music to help extend the session.
        Spotify only accepts a playlist URI in `play track` when it's active, so
        activate → shuffle → play the playlist, then bounce focus back to work."""
        _osa('tell application "Spotify" to activate', timeout=3)
        time.sleep(0.4)
        _osa('tell application "Spotify" to set shuffling to true', timeout=3)
        ok = _osa(f'tell application "Spotify" to play track "{self.focus_playlist}"', timeout=4)
        # Return focus to the work app so the user isn't left staring at Spotify.
        target = self.last_on_task_app
        if target and target.lower() not in NEVER_HIDE:
            time.sleep(0.3)
            _osa(f'tell application "{target}" to activate', timeout=3)
        print(f"  [autopilot] switched to focus music" + ("" if ok else " (Spotify not available)"))
        return ok

    NUDGE_COOLDOWN = 90.0
    DIP_MIN = 0.08            # focus must fall this far below peak to be a dip

    def assess_dip(self, focus, stress, engagement, work_min):
        """Decide what a focus dip MEANS. Returns (kind, message).
        kind: "break" (real fatigue) | "switch" (recoverable, push longer) | "ok".
        """
        if focus is None or self._peak_focus <= 0:
            return ("ok", "")
        drop = self._peak_focus - focus
        if drop < self.DIP_MIN:
            return ("ok", "")
        pct = int(drop / self._peak_focus * 100)
        # Real fatigue: deep drop + high stress + you've been at it a while.
        if stress is not None and stress > 0.55 and drop > 0.15 and work_min >= 25:
            return ("break",
                    f"Focus down {pct}% and stress is high after {work_min} min — take a real break.")
        # Recoverable: focus dipped but stress is low and you're still engaged.
        if (stress is None or stress < 0.5) and (engagement is None or engagement > 0.45):
            return ("switch",
                    f"Focus dipped {pct}% but stress is low and you're still engaged — "
                    f"you can work longer. Switch task for a 2-min reset, then push.")
        return ("ok", "")

    def _set_dnd(self, on: bool):
        if on == self._dnd:
            return
        name = self.dnd_on_name if on else self.dnd_off_name
        ok = _osa(f'do shell script "shortcuts run \\"{name}\\""', timeout=8)
        self._dnd = on
        print(f"  [autopilot] FLOW {'on' if on else 'off'} -> DND {'on' if on else 'off'}"
              + ("" if ok else f" (shortcut '{name}' missing)"))

    # --- main step, called per EEG sample ---
    def step(self, now: float, ctx, ms):
        if not self.enabled or ctx is None or ms is None:
            return
        focus = ms.focus
        if focus is None:
            return

        self._peak_focus = max(self._peak_focus, focus)
        distraction = self._is_distraction(ctx) and not self._on_goal(ctx)
        on_task = self._is_work_app(ctx) or self._on_goal(ctx)
        if on_task:
            self.last_on_task_app = getattr(ctx, "app_name", None) or self.last_on_task_app

        # Focus dip WHILE working (not scrolling): break vs switch/push decision.
        if on_task and not distraction and (now - self._last_nudge) >= self.NUDGE_COOLDOWN:
            work_min = int((now - self._session_start) / 60)
            kind, msg = self.assess_dip(focus, ms.stress, ms.engagement, work_min)
            if kind == "switch":
                # Recoverable dip -> switch to focus music, keep them going.
                self._notify("Brain: focus dip detected",
                             "Stress low, still engaged — calm focus music on to help you push longer.")
                self._play_focus_music()
                print(f"  [autopilot] SWITCH -> focus music. {msg}")
                self._last_nudge = now
            elif kind == "break":
                self._notify("Focus dropping", msg)
                print(f"  [autopilot] BREAK -> {msg}")
                self._last_nudge = now

        # DRIFT: low attention + on a distraction, sustained -> act
        if focus < self.DRIFT_FOCUS and distraction:
            self._drift_since = self._drift_since or now
            held = now - self._drift_since
            if held >= self.DRIFT_HOLD_SEC and (now - self._last_action) >= self.ACTION_COOLDOWN:
                self._hide_front_and_return(ctx)
                self._last_action = now
                self._drift_since = None
        else:
            self._drift_since = None

        # FLOW guard: sustained focus + on task -> DND on; otherwise off
        if self.flow_guard:
            locked = focus >= self.FLOW_FOCUS and not distraction
            if locked:
                self._flow_since = self._flow_since or now
                if now - self._flow_since >= self.FLOW_HOLD_SEC:
                    self._set_dnd(True)
            else:
                self._flow_since = None
                if focus < self.DRIFT_FOCUS or distraction:
                    self._set_dnd(False)

    def shutdown(self):
        """Restore environment on exit."""
        self._set_dnd(False)
