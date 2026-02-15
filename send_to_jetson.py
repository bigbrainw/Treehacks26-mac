"""
Stream EEG/brain data + user activity to Jetson.
Sends met, pow, mot, dev plus current app/window/context_type so Jetson agent can
decide if user needs feedback (e.g. break, focus aid).
Shows agent feedback in a small overlay window.
"""
import json
import os
import time
import threading
from pathlib import Path

from dotenv import load_dotenv
from cortex import Cortex
import requests

from activity import ActivityMonitor


JETSON_BASE = os.environ.get('JETSON_URL', 'https://8061-68-65-164-46.ngrok-free.app').rstrip('/')
JETSON_URL = f'{JETSON_BASE}/eeg'
SEND_INTERVAL_SEC = float(os.environ.get('SEND_INTERVAL', '2.0'))


class StreamToJetson:
    def __init__(self, app_client_id, app_client_secret, jetson_url=JETSON_URL, feedback_window=None, **kwargs):
        self.jetson_url = jetson_url
        self.feedback_window = feedback_window
        self.buffer = {'met': None, 'pow': None, 'mot': None, 'dev': None}
        self.send_count = 0
        self.activity = ActivityMonitor(poll_interval=SEND_INTERVAL_SEC)

        self.c = Cortex(app_client_id, app_client_secret, debug_mode=False, **kwargs)
        self.c.bind(create_session_done=self.on_create_session_done)
        self.c.bind(new_met_data=self.on_new_met_data)
        self.c.bind(new_pow_data=self.on_new_pow_data)
        self.c.bind(new_mot_data=self.on_new_mot_data)
        self.c.bind(new_dev_data=self.on_new_dev_data)
        self.c.bind(inform_error=self.on_inform_error)

    def start(self, streams=None, headset_id=''):
        self.streams = streams or ['met', 'pow', 'mot', 'dev']
        if headset_id:
            self.c.set_wanted_headset(headset_id)

        t = threading.Thread(target=self._send_loop, daemon=True)
        t.start()

        self.c.open()

    def _send_loop(self):
        while True:
            time.sleep(SEND_INTERVAL_SEC)
            self._flush()

    def _flush(self):
        streams_payload = {k: v for k, v in self.buffer.items() if v is not None}
        if not streams_payload:
            return

        ctx = self.activity.get_current_activity()
        context = ctx.to_dict() if ctx else {}

        body = {
            'timestamp': time.time(),
            'streams': streams_payload,
            'context': context,
        }

        try:
            r = requests.post(
                self.jetson_url,
                json=body,
                headers={
                    'Content-Type': 'application/json',
                    'ngrok-skip-browser-warning': '1',
                },
                timeout=5,
            )
            self.send_count += 1
            status = r.status_code
            print(f'[{self.send_count}] POST {self.jetson_url} -> {status}')
            if status != 200:
                print(f'  response: {r.text[:200]}')
            elif self.feedback_window and r.text:
                try:
                    data = r.json()
                    feedback = data.get('feedback') or data.get('message')
                    if feedback:
                        self.feedback_window.root.after(0, lambda t=feedback: self.feedback_window.update_feedback(t))
                except json.JSONDecodeError:
                    pass
        except requests.RequestException as e:
            print(f'[{self.send_count}] POST failed: {e}')

    def on_create_session_done(self, *args, **kwargs):
        self.c.sub_request(self.streams)

    def on_new_met_data(self, *args, **kwargs):
        self.buffer['met'] = kwargs.get('data')

    def on_new_pow_data(self, *args, **kwargs):
        self.buffer['pow'] = kwargs.get('data')

    def on_new_mot_data(self, *args, **kwargs):
        self.buffer['mot'] = kwargs.get('data')

    def on_new_dev_data(self, *args, **kwargs):
        self.buffer['dev'] = kwargs.get('data')

    def on_inform_error(self, *args, **kwargs):
        print('Cortex error:', kwargs.get('error_data'))


def main():
    from feedback_window import FeedbackWindow

    load_dotenv(Path(__file__).parent / '.env')
    client_id = os.environ.get('client_id') or os.environ.get('CORTEX_CLIENT_ID')
    client_secret = os.environ.get('client_secret') or os.environ.get('CORTEX_CLIENT_SECRET')
    jetson_base = os.environ.get('JETSON_URL', JETSON_BASE).rstrip('/')
    jetson_url = f'{jetson_base}/eeg'

    if not client_id or not client_secret:
        raise SystemExit('Missing credentials. Set client_id and client_secret in .env')

    feedback = FeedbackWindow()
    s = StreamToJetson(client_id, client_secret, jetson_url=jetson_url, feedback_window=feedback)

    t = threading.Thread(target=s.start, daemon=True)
    t.start()

    print(f'Sending to Jetson: {jetson_url} (every {SEND_INTERVAL_SEC}s)')
    print('Feedback window open. Close it to exit.')
    feedback.run()


if __name__ == '__main__':
    main()
