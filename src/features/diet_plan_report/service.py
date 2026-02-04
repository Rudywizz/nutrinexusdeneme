
from __future__ import annotations
from typing import Any, Dict

def build_payload(*, client: Dict[str, Any], plan: Any, fmt_date_ui) -> Dict[str, Any]:
    start_ui = fmt_date_ui(getattr(plan, "start_date", ""))
    end_ui = fmt_date_ui(getattr(plan, "end_date", ""))
    date_range = start_ui if not end_ui else f"{start_ui} – {end_ui}"

    return {
        "client": client or {},
        "plan": {
            "id": getattr(plan, "id", None),
            "title": getattr(plan, "title", "") or "Diyet Planı",
            "start_date": getattr(plan, "start_date", ""),
            "end_date": getattr(plan, "end_date", ""),
            "plan_text": getattr(plan, "plan_text", "") or "",
            "notes": getattr(plan, "notes", "") or "",
        },
        "date_range": date_range,
    }
