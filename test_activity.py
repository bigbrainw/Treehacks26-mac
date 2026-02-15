"""Test activity monitoring only - no Emotiv, no Jetson."""
import time

from activity import ActivityMonitor


def main():
    monitor = ActivityMonitor(poll_interval=2.0)

    def on_change(ctx, prev):
        print(f"  [CHANGE] {prev.display_name if prev else '—'} -> {ctx.display_name}")

    monitor.on_context_change(on_change)
    print("Monitoring active app/window (Ctrl+C to stop)...\n")

    while True:
        ctx = monitor.get_current_activity()
        if ctx:
            print(f"[{time.strftime('%H:%M:%S')}] {ctx.display_name}")
            print(f"         type={ctx.context_type} id={ctx.context_id}")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] (no context)")
        time.sleep(2)


if __name__ == "__main__":
    main()
