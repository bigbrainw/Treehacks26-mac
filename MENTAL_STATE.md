# Mental State from Emotiv Cortex API

How we parse the `met` (performance metrics) stream. **The array order is defined by `cols` from the subscribe response** – we use cols when available; otherwise fallback indices for EPOC/Insight/Flex.

## Emotiv met Stream Format (EPOC / Insight / Flex)

```
['eng.isActive','eng','exc.isActive','exc','lex','str.isActive','str','rel.isActive','rel','int.isActive','int','attention.isActive','attention']
```

| Index | Label         | Meaning |
|-------|---------------|---------|
| 0–1   | eng.isActive, eng | Engagement – immersion in activity (0–1) |
| 2–4   | exc.isActive, exc, lex | Excitement, long-term excitement |
| 5–6   | str.isActive, str | Stress – emotional tension when completing a task (0–1) |
| 7–8   | rel.isActive, rel | Relaxation – calm focus after intense work |
| 9–10  | int.isActive, int | Interest – attraction or aversion to stimuli |
| 11–12 | attention.isActive, attention | Attention – sustained focus on a single task |

All values are 0–1. `null` when signal quality is too poor.

## When to Call User "Confused" or "Stuck"

| State       | Conditions |
|-------------|------------|
| **Stuck**   | Low engagement (<0.35) + high stress (>0.55) + low attention (<0.4) |
| **Confused**| Low engagement (<0.4) + high stress (>0.5), or stress >0.55 |
| **Distracted** | Low attention (<0.35) + low engagement (<0.45) |
| **Focused** | Engagement ≥0.5, attention ≥0.4, stress <0.6 |

## Usage

- `mental_state_parser.parse_met_to_mental_state(metrics)` – parses raw `met` dict into `MentalStateSnapshot`
- `mental_state_parser.derive_mental_state_label(ms)` – returns `"confused"`, `"stuck"`, `"distracted"`, or `"focused"`

The app uses the derived label in `reading_help` payloads and for agent feedback.
