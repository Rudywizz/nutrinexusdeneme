from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional

DEFAULT_CLINICAL_THRESHOLDS: Dict[str, Any] = {
    # Measurement trend thresholds
    "weight_rate_info": 1.0,   # kg/week (abs)
    "weight_rate_warn": 2.0,   # kg/week (abs)
    "waist_info": 95.0,        # cm
    "waist_warn": 110.0,       # cm

    # Labs
    "crp_warn": 10.0,          # mg/L (typical)
    "hba1c_warn": 5.7,         # %
    "hba1c_critical": 6.5,     # %
    "ldl_warn": 160.0,         # mg/dL
    "ldl_critical": 190.0,     # mg/dL
}

META_KEY_THRESHOLDS = "clinical_thresholds_v1"


class SettingsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _get_meta(self, key: str) -> Optional[str]:
        cur = self.conn.execute("SELECT value FROM app_meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO app_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # --- Generic app settings (stored in app_meta) ---
    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Read a plain string setting from app_meta."""
        return self._get_meta(key) or default

    def set_value(self, key: str, value: str) -> None:
        """Write a plain string setting to app_meta."""
        self._set_meta(key, value)


    def set_default(self, key: str, value: str) -> None:
        """Set a default value only if the key does not exist yet."""
        cur = self.conn.execute("SELECT 1 FROM app_meta WHERE key=?", (key,))
        row = cur.fetchone()
        if row is None:
            self._set_meta(key, value)

    def get_float(self, key: str, default: float) -> float:
        raw = self._get_meta(key)
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except Exception:
            return default

    def get_int(self, key: str, default: int) -> int:
        raw = self._get_meta(key)
        if raw is None or raw == "":
            return default
        try:
            return int(float(raw))
        except Exception:
            return default

    def set_float(self, key: str, value: float) -> None:
        self._set_meta(key, str(float(value)))

    def set_int(self, key: str, value: int) -> None:
        self._set_meta(key, str(int(value)))

    def get_clinical_thresholds(self) -> Dict[str, Any]:
        raw = self._get_meta(META_KEY_THRESHOLDS)
        data: Dict[str, Any] = {}
        if raw:
            try:
                data = json.loads(raw) or {}
            except Exception:
                data = {}
        merged = dict(DEFAULT_CLINICAL_THRESHOLDS)
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged

    def save_clinical_thresholds(self, thresholds: Dict[str, Any]) -> None:
        # Store only keys we know; ignore unknowns for stability.
        cleaned = {}
        for k in DEFAULT_CLINICAL_THRESHOLDS.keys():
            if k in thresholds:
                cleaned[k] = thresholds[k]
        self._set_meta(META_KEY_THRESHOLDS, json.dumps(cleaned, ensure_ascii=False))