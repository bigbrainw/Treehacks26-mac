"""
Test script: subscribe to performance metrics (met) only.
met stream: engagement, excitement, stress, relaxation, interest, attention
On free tier: ~0.1 Hz (1 sample every 10 seconds)
"""
from cortex import Cortex


class SubMet:
    def __init__(self, app_client_id, app_client_secret, **kwargs):
        self.c = Cortex(app_client_id, app_client_secret, debug_mode=False, **kwargs)
        self.c.bind(create_session_done=self.on_create_session_done)
        self.c.bind(new_data_labels=self.on_new_data_labels)
        self.c.bind(new_met_data=self.on_new_met_data)
        self.c.bind(inform_error=self.on_inform_error)

    def start(self, headset_id=''):
        if headset_id:
            self.c.set_wanted_headset(headset_id)
        self.c.open()

    def on_create_session_done(self, *args, **kwargs):
        print("Session ready, subscribing to 'met'...")
        self.c.sub_request(['met'])

    def on_new_data_labels(self, *args, **kwargs):
        data = kwargs.get('data')
        print(f"met labels: {data.get('labels', [])}")

    def on_new_met_data(self, *args, **kwargs):
        data = kwargs.get('data')
        print("pm data:", data)

    def on_inform_error(self, *args, **kwargs):
        print("Error:", kwargs.get('error_data'))


def main():
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / '.env')
    client_id = os.environ.get('client_id') or os.environ.get('CORTEX_CLIENT_ID')
    client_secret = os.environ.get('client_secret') or os.environ.get('CORTEX_CLIENT_SECRET')

    if not client_id or not client_secret:
        raise SystemExit('Missing credentials. Set client_id and client_secret in .env')

    s = SubMet(client_id, client_secret)
    s.start()


if __name__ == '__main__':
    main()
