"""Emotiv Cortex client wrapper – streams met (mental state) to Jetson."""
import time
import threading

from cortex import Cortex
from activity import ActivityMonitor

import config


class EmotivCortexClient:
    """Streams EEG metrics (met = mental state) from Emotiv headset."""

    def __init__(
        self,
        client_id=None,
        client_secret=None,
        on_metrics=None,
        streams=None,
        profile_name=None,
    ):
        self.client_id = client_id or config.EMOTIV_CLIENT_ID
        self.client_secret = client_secret or config.EMOTIV_CLIENT_SECRET
        self.on_metrics = on_metrics
        self.streams = streams or ["met"]
        self.profile_name = profile_name or getattr(config, "EMOTIV_PROFILE", "") or "Elijah"
        self.activity = ActivityMonitor(poll_interval=config.POLL_INTERVAL)
        self._cortex = None
        self._thread = None

    def connect(self):
        """Connect to Cortex and start streaming."""
        self._cortex = Cortex(
            self.client_id,
            self.client_secret,
            debug_mode=False,
        )
        self._cortex.set_wanted_profile(self.profile_name)
        self._cortex.bind(create_session_done=self._on_create_session)
        self._cortex.bind(query_profile_done=self._on_query_profile)
        self._cortex.bind(load_unload_profile_done=self._on_load_profile)
        self._cortex.bind(new_met_data=self._on_met)
        self._cortex.bind(new_data_labels=self._on_data_labels)
        self._cortex.bind(inform_error=self._on_error)
        self._met_cols = []  # cols from subscription; order of values in met array

        self._thread = threading.Thread(target=self._cortex.open, daemon=True)
        self._thread.start()

    def _subscribe_streams(self):
        """Subscribe to data streams. Called after profile is loaded."""
        self._cortex.sub_request(self.streams)

    def _on_create_session(self, *args, **kwargs):
        """Session created → query profiles, then load before subscribing."""
        print("  Emotiv: session created, loading profile...")
        self._cortex.query_profile()

    def _on_query_profile(self, *args, **kwargs):
        """Profile list received → load our profile (or create if missing)."""
        profiles = kwargs.get("data") or []
        # Case-insensitive match (Emotiv may use "Elijah" vs "elijah")
        matched = next((p for p in profiles if p.lower() == self.profile_name.lower()), None)
        if matched:
            self.profile_name = matched  # Use exact name from Emotiv
            self._cortex.set_wanted_profile(matched)
            self._cortex.get_current_profile()
        else:
            print(f"  Emotiv: profile '{self.profile_name}' not found, creating...")
            self._cortex.setup_profile(self.profile_name, "create")

    def _on_load_profile(self, *args, **kwargs):
        """Profile loaded → subscribe to streams (same flow as Emotiv BCI app)."""
        is_loaded = kwargs.get("isLoaded", False)
        if is_loaded:
            print(f"  Emotiv: profile '{self.profile_name}' loaded")
            self._subscribe_streams()
        else:
            print("  Emotiv: profile unloaded, loading ours...")
            self._cortex.setup_profile(self.profile_name, "load")

    def _on_data_labels(self, *args, **kwargs):
        """Capture met stream cols from subscription – array order matches cols."""
        labels = kwargs.get("data") or {}
        if labels.get("streamName") == "met":
            self._met_cols = labels.get("labels") or []
            print(f"  Emotiv: met cols = {self._met_cols}")

    def _on_met(self, *args, **kwargs):
        data = kwargs.get("data")
        if data and self.on_metrics:
            metrics = {
                "met": data.get("met"),
                "time": data.get("time", time.time()),
                "cols": getattr(self, "_met_cols", []) or None,
            }
            self.on_metrics(metrics)

    def _on_error(self, *args, **kwargs):
        print("Cortex error:", kwargs.get("error_data"))

    def close(self):
        if self._cortex:
            try:
                self._cortex.close()
            except Exception:
                pass
