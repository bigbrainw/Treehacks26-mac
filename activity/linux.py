"""Linux (X11) activity detection using xdotool."""

import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class WindowInfo:
    app_name: str
    window_title: str
    window_id: Optional[str] = None

    @property
    def context_id(self) -> str:
        return f"{self.app_name}::{self.window_title}"


def get_active_window_x11() -> Optional[WindowInfo]:
    """Get active window on X11 via xdotool. Returns None if xdotool unavailable."""
    try:
        win_id = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=1
        )
        if win_id.returncode != 0 or not win_id.stdout.strip():
            return None

        wid = win_id.stdout.strip()
        win_name = subprocess.run(
            ["xdotool", "getwindowname", wid],
            capture_output=True, text=True, timeout=1
        )
        # xdotool getwindowname returns full title; we use it for both app & window
        title = win_name.stdout.strip() if win_name.returncode == 0 else ""
        # Try to get window class (app hint)
        wm_class = subprocess.run(
            ["xprop", "-id", wid, "WM_CLASS"],
            capture_output=True, text=True, timeout=1
        )
        app = "unknown"
        if wm_class.returncode == 0 and wm_class.stdout:
            parts = wm_class.stdout.split('"')
            if len(parts) >= 4:
                app = parts[3]  # instance name
        return WindowInfo(app_name=app, window_title=title, window_id=wid)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def infer_context_type(app_name: str, window_title: str) -> str:
    """Infer context type. Same logic as macOS for consistency."""
    app_lower = app_name.lower()
    title_lower = window_title.lower()

    browsers = ["safari", "chrome", "firefox", "brave", "edge", "opera"]
    if any(b in app_lower for b in browsers):
        if "http" in title_lower or "www." in title_lower or ".com" in title_lower:
            return "website"
        return "browser"

    editors = ["cursor", "visual studio code", "code", "vim", "sublime"]
    if any(e in app_lower for e in editors):
        return "file"

    if "terminal" in app_lower or "iterm" in app_lower:
        return "terminal"

    return "app"
