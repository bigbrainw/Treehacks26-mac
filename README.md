# Emotiv Cortex API Python Examples

This folder contains the official Emotiv Cortex API Python examples from [Emotiv/cortex-example](https://github.com/Emotiv/cortex-example).

## Requirements

- Python 2.7+ or Python 3.4+
- Install dependencies: `pip install -r requirements.txt`

## Getting Started

1. **Download EMOTIV Launcher** from [emotiv.com](https://www.emotiv.com/products/emotiv-launcher)
2. **Register your Cortex App** to get Client ID and Client Secret: https://emotiv.gitbook.io/cortex-api#create-a-cortex-app
3. Update `your_app_client_id` and `your_app_client_secret` in each script

## Files

| File | Description |
|------|-------------|
| `cortex.py` | Core Cortex API wrapper (WebSocket, JSON-RPC, event handling) |
| `sub_data.py` | Subscribe to EEG, motion, performance metrics, band power |
| `record.py` | Record and export data to CSV/EDF |
| `marker.py` | Inject markers during recording |
| `mental_command_train.py` | Train mental command actions (push, pull, etc.) |
| `facial_expression_train.py` | Train facial expression actions |
| `live_advance.py` | Live mental command data + sensitivity control |
| `query_records.py` | Query, download, and export records |

## Focus Agent (Main App)

**Real activity + time-on-page + EEG → Jetson.** When you stay on difficult content too long, triggers agent for help. Feedback in overlay.

```bash
python app.py                    # Real activity + real Emotiv EEG
python app.py --mock             # Mock EEG (no headset, for testing)
python app.py --long 45           # 45 sec on page before trigger
python app.py --no-feedback       # No overlay window
```

- **Activity:** Real app/window/URL via ActivityMonitor (lecture, reading, coding, etc.)
- **Time:** SessionTracker fires at `warn` (5s) and `long` (10s) – stuck trigger at 10s
- **EEG:** Real Emotiv headset (default); `--mock` for testing without headset
- **Mental command:** Requires trained profile; set `EMOTIV_PROFILE` in .env to match your Emotiv BCI profile name
- **On long threshold:** POSTs to Jetson `/eeg` with context + duration + mental_state, shows feedback
- **Streams:** activity (with `duration_seconds`), eeg, mental_state over WebSocket

## Jetson Collector (WebSocket)

Legacy/standalone collector: stream EEG + activity to Jetson.

```bash
python collector.py --url wss://YOUR_NGROK_URL --show-feedback
python collector_mock.py --url wss://YOUR_NGROK_URL --show-feedback
```

- **Sends:** `eeg`, `mental_state`, `activity` over WebSocket
- **Receives:** Agent feedback (`{"type": "feedback", "feedback": "..."}`) in overlay
- **Processor:** Jetson runs processor (HTTP + WebSocket)

## Data Structures

See [DATA_STRUCTURES.md](DATA_STRUCTURES.md) for the exact JSON payloads sent to ngrok: WebSocket (`activity`, `eeg`, `mental_state`, `reading_help`) and HTTP POST `/eeg`.

## Documentation

Full API docs: https://emotiv.gitbook.io/cortex-api/
