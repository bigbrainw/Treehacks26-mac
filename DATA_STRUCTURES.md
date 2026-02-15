# Data Structures Sent to Ngrok / Jetson Backend

Two transport modes: **WebSocket** (streaming) and **HTTP POST** (on stuck trigger).

**Canonical agent request:** See `agent_request.py` and `AGENT_REQUEST.json` for the exact JSON format.

---

## 1. WebSocket (e.g. `wss://YOUR_NGROK.ngrok-free.app`)

JSON messages sent every ~2 seconds (configurable via `SEND_INTERVAL`). Each message has a `type` field.

### 1a. `activity`

```json
{
  "type": "activity",
  "timestamp": 1739612345.678,
  "activity": {
    "app_name": "Chrome",
    "window_title": "CS224N Lecture 5 — Backpropagation | Stanford",
    "context_type": "website",
    "context_id": "Chrome::cs224n.stanford.edu",
    "reading_section": null,
    "duration_seconds": 12.5
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `app_name` | string | Browser/app (Chrome, Safari, VS Code, etc.) |
| `window_title` | string | Tab/window title |
| `context_type` | string | `website` \| `file` \| `terminal` \| `browser` \| `app` |
| `context_id` | string | Stable id for context (e.g. `App::domain`) |
| `reading_section` | string? | Selected text, URL section, or "Page N of M" (PDF) |
| `page_number` | int? | Current page (PDFs; optional) |
| `file_path` | string? | Full path to file (optional) |
| `duration_seconds` | float? | Time spent in this context |

---

### 1b. `eeg`

```json
{
  "type": "eeg",
  "timestamp": 1739612345.678,
  "eeg": {
    "metrics": {
      "met": [true, 0.65, true, 0.42, 0.38, true, 0.55, true, 0.72, true, 0.48, true, 0.58],
      "time": 1739612345.678
    }
  },
  "activity": {
    "app_name": "Chrome",
    "window_title": "Lecture Notes...",
    "context_type": "website",
    "context_id": "Chrome::example.edu",
    "reading_section": null,
    "duration_seconds": 12.5
  }
}
```

`metrics.met` is the Emotiv performance metrics array (engagement, stress, etc.).

---

### 1c. `mental_state`

```json
{
  "type": "mental_state",
  "timestamp": 1739612345.678,
  "mental_state": {
    "engagement": 0.55,
    "stress": 0.35,
    "relaxation": 0.45,
    "focus": 0.52,
    "excitement": null,
    "interest": null,
    "metrics": {
      "met": [true, 0.65, true, 0.42, 0.38],
      "time": 1739612345.678
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `engagement` | float? | 0–1 |
| `stress` | float? | 0–1 |
| `relaxation` | float? | 0–1 |
| `focus` | float? | 0–1 |
| `excitement` | float? | 0–1 |
| `interest` | float? | 0–1 |
| `metrics` | dict | Raw `met` from Emotiv |

---

### 1d. `reading_help` (on stuck trigger, ~10s on same page)

```json
{
  "type": "reading_help",
  "timestamp": 1739612345.678,
  "activity": {
    "app_name": "Chrome",
    "window_title": "Complex Paper — arXiv",
    "context_type": "website",
    "context_id": "Chrome::arxiv.org",
    "reading_section": null,
    "duration_seconds": 10.2
  },
  "mental_state": {
    "engagement": 0.32,
    "stress": 0.58,
    "relaxation": 0.42,
    "focus": 0.35,
    "excitement": null,
    "interest": null,
    "metrics": {"met": [...], "time": ...}
  },
  "user_feedback": null
}
```

Raw mental state metrics sent to backend; backend interprets. On follow-up (still stuck): `user_feedback` = `"(Still on this – try a different angle)"`.

---

---

## 2. HTTP POST `POST /eeg`

Sent when stuck trigger fires (after ~10s on same page). Used for immediate feedback.

**URL:** `https://YOUR_NGROK.ngrok-free.app/eeg`  
**Headers:** `Content-Type: application/json`, `ngrok-skip-browser-warning: 1`

```json
{
  "timestamp": 1739612345.678,
  "streams": {"met": {"met": [...], "time": 1739612345.678}},
  "context": {
    "app_name": "Chrome",
    "window_title": "Lecture Notes...",
    "context_type": "website",
    "context_id": "Chrome::example.edu",
    "duration_seconds": 10.2,
    "mental_state": {
      "engagement": 0.32,
      "stress": 0.58,
      "relaxation": 0.42,
      "focus": 0.35,
      "excitement": null,
      "interest": null,
      "metrics": {"met": [...], "time": ...}
    },
    "user_feedback": null
  }
}
```

**Expected response:** `{"feedback": "Help message here"}` or `{"message": "..."}`.

---

## Jetson → Client (WebSocket)

```json
{
  "type": "feedback",
  "feedback": "Consider taking a short break or re-reading the key definitions."
}
```
