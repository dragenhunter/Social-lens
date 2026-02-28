"""Per-account scoring utilities.

This module computes a lightweight heuristic score for accounts used by the
account-rotation logic. The scoring combines several signals when available:

- `disabled` flag (immediate zero score)
- recent failures (penalize)
- success_rate (preferred)
- recency of last_success (favor recently-working accounts)
- manual `weight` override to bump preferred accounts

The function is defensive: missing fields are handled with sensible defaults.
"""

from datetime import datetime, timedelta
from typing import Dict, Any


def _parse_iso(s: str):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def score_account(account: Dict[str, Any]) -> float:
    """Return a score (higher is better) for the given account.

    Expected account keys (optional):
    - `disabled`: bool
    - `failures`: int
    - `success_rate`: float (0..1)
    - `last_success`: ISO timestamp
    - `weight`: numeric override multiplier
    """
    if not isinstance(account, dict):
        return 0.0

    if account.get("disabled"):
        return 0.0

    score = 0.5

    # Favor higher success_rate
    sr = account.get("success_rate")
    if isinstance(sr, (int, float)):
        score += float(sr) * 0.4

    # Penalize recent failures
    failures = account.get("failures")
    if isinstance(failures, int) and failures > 0:
        score -= min(failures * 0.05, 0.4)

    # Favor accounts with recent successful activity
    last_s = account.get("last_success")
    if isinstance(last_s, str):
        dt = _parse_iso(last_s)
        if dt:
            age = datetime.utcnow() - dt
            if age < timedelta(hours=6):
                score += 0.2
            elif age < timedelta(days=1):
                score += 0.1
            elif age < timedelta(days=7):
                score += 0.02

    # Manual weight multiplier
    weight = account.get("weight")
    if isinstance(weight, (int, float)):
        score *= float(weight)

    # clamp
    try:
        return max(0.0, min(score, 10.0))
    except Exception:
        return 0.0

