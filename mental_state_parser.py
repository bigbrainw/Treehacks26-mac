"""
Parse Emotiv Cortex met stream into mental state (engagement, stress, focus, etc.)
and derive when user is confused/stuck for help triggers.

Emotiv met stream format (EPOC/Insight/Flex):
  ['eng.isActive','eng','exc.isActive','exc','lex','str.isActive','str','rel.isActive','rel','int.isActive','int','attention.isActive','attention']
  or older: ...'foc.isActive','foc' instead of attention

Metrics (0-1): eng=engagement, exc=excitement, str=stress, rel=relaxation, int=interest, attention/foc=focus
"""
from typing import Optional

from data_schema import MentalStateSnapshot


# Fallback indices for EPOC/Insight/Flex (Cortex API data-sample-object)
FALLBACK_INDICES = {"eng": 1, "exc": 3, "lex": 4, "str": 6, "rel": 8, "int": 10, "attention": 12, "foc": 12}


def _indices_from_cols(cols: list) -> dict[str, int]:
    """Build metric name -> index from cols. Use only numeric labels (not .isActive)."""
    out = {}
    for i, label in enumerate(cols):
        if label in ("eng", "exc", "lex", "str", "rel", "int", "attention", "foc", "cognitiveStress"):
            out[label] = i
    return out


def parse_met_to_mental_state(metrics: dict) -> MentalStateSnapshot:
    """
    Parse raw Cortex met data into MentalStateSnapshot.
    Uses cols from subscription when available (order varies by headset); else fallback indices.
    MN8 has cognitiveStress instead of str.
    """
    met_arr = metrics.get("met")
    if not met_arr or not isinstance(met_arr, (list, tuple)):
        return MentalStateSnapshot(metrics=metrics)

    cols = metrics.get("cols")
    indices = _indices_from_cols(cols) if cols else FALLBACK_INDICES
    arr = met_arr

    def _val(label: str):
        idx = indices.get(label)
        if idx is not None and 0 <= idx < len(arr):
            v = arr[idx]
            if v is not None and not isinstance(v, bool):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None

    stress = _val("str") or _val("cognitiveStress")
    focus = _val("attention") or _val("foc")
    engagement = _val("eng")
    excitement = _val("exc")
    relaxation = _val("rel")
    interest = _val("int")

    return MentalStateSnapshot(
        engagement=engagement,
        stress=stress,
        relaxation=relaxation,
        focus=focus,
        excitement=excitement,
        interest=interest,
        metrics=metrics,
    )


def derive_mental_state_label(ms: MentalStateSnapshot | None) -> str:
    """
    Map Emotiv metrics to confused/stuck/distracted/focused for the agent.

    Rules (based on Emotiv Performance Metrics documentation):
    - Stuck/Confused: low engagement + high stress + low attention = struggling, can't progress
    - Distracted: low attention/focus, low engagement = mind elsewhere
    - Focused: decent engagement, manageable stress, decent attention
    """
    if ms is None:
        return "stuck"

    eng = ms.engagement if ms.engagement is not None else 0.5
    stress = ms.stress if ms.stress is not None else 0.4
    focus = ms.focus if ms.focus is not None else 0.5
    relaxation = ms.relaxation if ms.relaxation is not None else 0.5

    # Confused/stuck: not immersed, high tension, can't sustain focus
    if eng < 0.4 and stress > 0.5:
        return "confused"  # or "stuck" - struggling with content
    if eng < 0.35 and stress > 0.55 and focus < 0.4:
        return "stuck"

    # Distracted: low focus, low engagement
    if focus < 0.35 and eng < 0.45:
        return "distracted"

    # Focused: engaged, manageable stress
    if eng >= 0.5 and focus >= 0.4 and stress < 0.6:
        return "focused"

    # Default: neutral / slight struggle
    if stress > 0.55:
        return "confused"
    return "focused"
