"""Test the feedback window in isolation (no Emotiv, no Jetson)."""
import threading
import time

from feedback_window import FeedbackWindow


def main():
    f = FeedbackWindow()

    def inject():
        time.sleep(2)
        f.root.after(0, lambda: f.update_feedback("Consider taking a short break – stress is elevated."))
        time.sleep(4)
        f.root.after(0, lambda: f.update_feedback("You've been focused for a while. Stretch or look away for 20 seconds."))

    threading.Thread(target=inject, daemon=True).start()
    print("Feedback window open. Sample messages will appear in 2s and 6s.")
    f.run()


if __name__ == "__main__":
    main()
