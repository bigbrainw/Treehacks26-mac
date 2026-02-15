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

## Documentation

Full API docs: https://emotiv.gitbook.io/cortex-api/
