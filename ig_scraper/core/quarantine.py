import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Any


STATE_PATH = Path(__file__).resolve().parent.parent / "storage" / "state.json"


def _ensure_state_file() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        STATE_PATH.write_text("{}", encoding="utf-8")


def _read_state() -> Dict[str, Any]:
    _ensure_state_file()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def quarantine_account(username: str, reason: str) -> None:
    if not username:
        return
    state = _read_state()
    quarantined = state.setdefault("quarantined_accounts", {})
    quarantined[username] = {
        "reason": reason,
        "since": datetime.utcnow().isoformat(),
        "active": True,
    }
    _write_state(state)


def is_quarantined(username: str) -> Tuple[bool, Dict[str, Any]]:
    if not username:
        return False, {}
    state = _read_state()
    quarantined = state.get("quarantined_accounts") or {}
    if not isinstance(quarantined, dict):
        return False, {}
    entry = quarantined.get(username) or {}
    if isinstance(entry, dict) and entry.get("active") is True:
        return True, entry
    return False, {}


def clear_quarantine(username: str) -> bool:
    if not username:
        return False
    state = _read_state()
    quarantined = state.get("quarantined_accounts") or {}
    if not isinstance(quarantined, dict) or username not in quarantined:
        return False
    quarantined.pop(username, None)
    state["quarantined_accounts"] = quarantined
    _write_state(state)
    return True


def clear_all_quarantines() -> int:
    state = _read_state()
    quarantined = state.get("quarantined_accounts") or {}
    if not isinstance(quarantined, dict):
        quarantined = {}
    count = len(quarantined)
    state["quarantined_accounts"] = {}
    _write_state(state)
    return count
