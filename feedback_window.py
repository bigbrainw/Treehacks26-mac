"""
Small overlay window to display agent feedback to the user.
Polls GET /feedback from the Jetson; expects {"feedback": "message"}.
"""

import threading
import time
from pathlib import Path

import tkinter as tk

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

FEEDBACK_URL = "http://localhost:8765/feedback"


class FeedbackWindow:
    """Floating window showing the latest agent feedback."""

    def __init__(self, width: int = 320, height: int = 120, poll_url=None, use_poll=None):
        self.root = tk.Tk()
        self.root.title("Agent Feedback")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a2e", highlightbackground="#16213e")
        x = self.root.winfo_screenwidth() - width - 20
        self.root.geometry(f"{width}x{height}+{x}+20")

        self._poll_url = poll_url or FEEDBACK_URL
        # use_poll=False: manual updates only (e.g. WebSocket push). use_poll=True: poll URL.
        self._should_poll = use_poll if use_poll is not None else (poll_url is not None)
        self._last_feedback = ""
        self._polling = True

        # Content frame
        frame = tk.Frame(self.root, bg="#1a1a2e", padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text="Agent",
            font=("Helvetica", 10),
            fg="#a0a0a0",
            bg="#1a1a2e",
        ).pack(anchor=tk.W)

        self.feedback_label = tk.Label(
            frame,
            text="Waiting for feedback...",
            font=("Helvetica", 13),
            fg="#e8e8e8",
            bg="#1a1a2e",
            wraplength=width - 32,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self.feedback_label.pack(anchor=tk.W, fill=tk.BOTH, expand=True)

    def update_feedback(self, text: str) -> None:
        """Update the displayed feedback. Thread-safe via root.after(0, ...)."""
        def _set():
            self.feedback_label.config(text=text or "—")
        try:
            self.root.after(0, _set)
        except tk.TclError:
            pass

    def _poll(self) -> None:
        """Background thread: poll GET /feedback and update window."""
        headers = {"ngrok-skip-browser-warning": "1"}
        while self._polling and _REQUESTS_AVAILABLE:
            try:
                r = requests.get(self._poll_url, headers=headers, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    msg = (data.get("feedback") or data.get("message") or "").strip()
                    if msg and msg != self._last_feedback:
                        self._last_feedback = msg
                        self.update_feedback(msg)
            except Exception:
                pass
            time.sleep(2)

    def run(self) -> None:
        """Start poll thread only if poll_url was explicitly set; then mainloop."""
        if _REQUESTS_AVAILABLE and self._should_poll:
            t = threading.Thread(target=self._poll, daemon=True)
            t.start()
        self.root.mainloop()

    def stop(self) -> None:
        """Stop polling (call before destroying)."""
        self._polling = False


def create_and_run_feedback_window(poll_url=None):
    """Create the window and run. Polls Jetson GET /feedback for agent messages."""
    w = FeedbackWindow(poll_url=poll_url)
    w.run()
    return w


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Agent feedback overlay - polls Jetson /feedback")
    p.add_argument("--url", default=FEEDBACK_URL, help="URL to poll, e.g. http://JETSON_IP:8765/feedback")
    args = p.parse_args()
    create_and_run_feedback_window(poll_url=args.url)
