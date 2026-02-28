"""Account rotation utilities.

`pick_account` chooses an account from the available pool. Selection favors
accounts with higher reputation (from `core.reputation`) and avoids accounts
that are marked as on cooldown (optionally by checking `account.get('cooldown')`).
The function is intentionally synchronous and lightweight — async cooldown
checks are handled elsewhere when needed.
"""

import random
from typing import List, Optional, Dict
from . import reputation


def pick_account(pool: List[Dict]) -> Optional[Dict]:
    """Return the best account from `pool` or None.

    Heuristic:
    - Filter out accounts explicitly marked with `account.get('disabled')`.
    - Prefer accounts with higher `reputation.score_account(account)`.
    - Break ties randomly to avoid deterministic selection.
    """
    if not pool:
        return None

    candidates = [a for a in pool if not a.get("disabled")]
    if not candidates:
        return None

    # score each account using reputation; default 0 for missing scores
    scored = []
    for a in candidates:
        try:
            s = reputation.score_account(a) or 0
        except Exception:
            s = 0
        scored.append((s, random.random(), a))

    # sort by score desc, break ties by random value
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]

