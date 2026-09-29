# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Focus Agent** — a macOS/Linux client that watches what the user is doing (active app / window / URL / PDF page), tracks how long they linger on one context, and streams EEG "mental state" from an Emotiv headset. When the user is stuck on hard content too long, it asks a remote **Jetson backend** (over WebSocket + HTTP, tunneled via ngrok) for help and shows the reply in a Tkinter overlay. The Jetson backend / agent is **not in this repo** — this side only produces payloads and renders feedback.

The repo also vendors the official **Emotiv Cortex API Python examples** (`cortex.py`, `sub_data.py`, `record.py`, `marker.py`, `mental_command_train.py`, `facial_expression_train.py`, `live_advance.py`, `query_records.py`) — reference/standalone scripts, largely independent of the Focus Agent app.

## Commands

```bash
pip install -r requirements.txt          # websocket-client, python-dispatch, python-dotenv, requests
python app.py                            # main app: real activity + MOCK eeg (no headset needed)
python app.py --eeg                      # real Emotiv headset (needs EMOTIV Launcher running + creds)
python app.py --eeg --profile Elijah     # use a specific trained BCI profile
python app.py --long 45                  # 45s on a page before the stuck trigger fires
python app.py --no-feedback              # no overlay window
python app.py --url https://xxxx.ngrok-free.app   # override Jetson base URL

python check_emotiv_creds.py             # verify EMOTIV creds load; -32021 troubleshooting
```

Tests are ad-hoc runnable scripts (no pytest harness): `python test_on_mac.py`, `python test_activity.py`, `python test_feedback_window.py`, `python test_met.py`, `python test_pdf_stuck.py`, `python live_reading_test.py`.

Default EEG is **mock**; pass `--eeg` for the real headset. Real EEG requires the EMOTIV Launcher app running locally and the app authorized under its EmotivID.

## Configuration

All config flows through `config.py`, which loads `.env` (see `.env.example`). Key points:
- Emotiv creds accept **either** `EMOTIV_CLIENT_ID`/`EMOTIV_CLIENT_SECRET` **or** lowercase `client_id`/`client_secret`.
- `EMOTIV_PROFILE` must match a profile name trained in the Emotiv BCI app for mental commands to work.
- `JETSON_URL` / `JETSON_WS_URL` point at the ngrok tunnel; `JETSON_BASE` (HTTP) is derived from the WS URL if unset.
- Session thresholds in `config.py` are set **low for testing** (`LONG_SESSION_THRESHOLD=30`, `WARN=20`); prod values are 180/120. CLI flags override.

## Architecture

`app.py::run_app` is the orchestrator. It spins up daemon threads that share `AppState` (mental state, mutex-guarded):

1. **WebSocket thread** — persistent connection to Jetson; sends stream payloads, receives `{"type":"feedback"}` for the overlay.
2. **EEG thread** — either `mock_eeg_loop` (synthetic `met` arrays + periodic mental commands) or, with `--eeg`, `EmotivCortexClient` (`eeg.py`) wrapping `cortex.py` and an `activity_sender`.
3. **Poll loop** — reads current activity, feeds `SessionTracker`.

**Data flow:** `ActivityMonitor` (context) + Emotiv `met`/`com` streams → per-tick `activity` / `eeg` / `mental_state` WebSocket messages. `SessionTracker` (`time_tracker.py`) fires `WARN` / `LONG` / `FOLLOW_UP` events; on `LONG`/`FOLLOW_UP`, `on_session_event` sends a `reading_help` WS message **and** `POST /eeg` for immediate feedback shown in the overlay.

**Payload contract is centralized** — do not hand-roll payloads:
- `data_schema.py` — dataclasses (`ActivitySnapshot`, `EEGMetricsSnapshot`, `MentalStateSnapshot`, `MentalCommandSnapshot`, `CollectorPayload`).
- `agent_request.py` — canonical help-request builders (`build_agent_request`, `build_post_eeg_body`, `build_reading_help_ws_message`); mirrored in `AGENT_REQUEST.json`.
- `DATA_STRUCTURES.md` — the exact JSON sent over WS and HTTP. Keep these in sync when changing payloads.

**Mental-state parsing** — `mental_state_parser.py` turns the raw Emotiv `met` array into a `MentalStateSnapshot`. Array order comes from the subscription `cols` when available, else fixed fallback indices. `MENTAL_STATE.md` documents the index layout and the confused/stuck/distracted/focused label thresholds.

**Platform activity** — `activity/__init__.py` picks `activity/macos.py` or `activity/linux.py` (X11) at runtime. macOS uses AppleScript/`osascript` to read browser URLs, selected text, and PDF page numbers.

**Overlay exclusion** — the Tkinter `FeedbackWindow` is itself an app window. `_is_overlay(ctx)` detects when it's focused; the app then substitutes `last_real_context` so the overlay never counts as the tracked activity. Preserve this whenever touching session/context logic.

**Mental command → scroll** — a `lift` command above `lift_power_threshold` while viewing a PDF or reels (`_is_pdf` / `_is_reels`) sends Page Down via `osascript` (rate-limited by `LIFT_SCROLL_COOLDOWN_SEC`), first activating the target app. Requires Accessibility permission for Terminal/Python.

## Legacy / alternate paths

- `collector.py` / `collector_mock.py` — standalone WebSocket collectors, predecessor to `app.py`. `send_to_jetson.py` / `send_sample_to_jetson.py` construct the Jetson URL dynamically.
- `config.py` contains pizza-ordering / Uber Eats / Anthropic-agent settings for features not present on this side of the codebase — treat as backend-side or deprecated unless you find the consumer.
