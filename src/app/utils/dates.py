from __future__ import annotations

from datetime import datetime, date
from typing import Optional

def _try_parse(s: str) -> Optional[datetime]:
    # be defensive: callers may pass dict/objects
    if s is None:
        s = ""
    elif isinstance(s, dict):
        # common shapes
        for k in ("date", "datetime", "measured_at", "taken_at", "value", "text"):
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                s = v
                break
        else:
            s = str(s)
    elif not isinstance(s, str):
        s = str(s)
    s = s.strip()
    if not s:
        return None
    # Common formats stored in app
    fmts = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Last resort: datetime.fromisoformat (handles many ISO variants)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def format_tr_date(value: str) -> str:
    """Return DD.MM.YYYY for a stored date string; if cannot parse, return original."""
    dt = _try_parse(value)
    if not dt:
        return value
    return dt.strftime("%d.%m.%Y")

def format_tr_datetime(value: str) -> str:
    """Return DD.MM.YYYY HH:MM for a stored datetime string; if cannot parse, return original."""
    dt = _try_parse(value)
    if not dt:
        return value
    return dt.strftime("%d.%m.%Y %H:%M")