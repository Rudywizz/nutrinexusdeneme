from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple
import sqlite3
from datetime import datetime
import uuid

from src.services.labs_parser import LabRow

ISO_FMT = "%Y-%m-%dT%H:%M:%S"

def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).strftime(ISO_FMT)

class LabsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_import(self, client_id: str, source_path: str) -> str:
        import_id = str(uuid.uuid4())
        p = Path(source_path)
        self.conn.execute(
            "INSERT INTO lab_imports(id, client_id, source_filename, source_path, imported_at) VALUES(?,?,?,?,?)",
            (import_id, client_id, p.name, str(p), _now_iso())
        )
        self.conn.commit()
        return import_id

    def save_rows(self, import_id: str, client_id: str, rows: List[LabRow], taken_at_iso: Optional[str] = None) -> None:
        created_at = _now_iso()
        taken_at = taken_at_iso or created_at
        for r in rows:
            self.conn.execute(
                """INSERT INTO lab_results(
                    import_id, client_id, taken_at,
                    test_name, result_text, result_value, unit,
                    ref_text, ref_low, ref_high, ref_mode, status, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    import_id, client_id, taken_at,
                    r.test_name, r.result_text, r.result_value, r.unit or "",
                    r.ref_text or "", r.ref.low, r.ref.high, r.ref.mode, r.status, created_at
                )
            )
        self.conn.commit()

    def list_imports(self, client_id: str, limit: int = 20) -> List[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM lab_imports WHERE client_id=? ORDER BY imported_at DESC LIMIT ?",
            (client_id, limit)
        )
        return cur.fetchall()

    def list_results_for_import(self, import_id: str) -> List[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM lab_results WHERE import_id=? ORDER BY id ASC",
            (import_id,)
        )
        return cur.fetchall()

    def latest_import_id(self, client_id: str) -> Optional[str]:
        cur = self.conn.execute(
            "SELECT id FROM lab_imports WHERE client_id=? ORDER BY imported_at DESC LIMIT 1",
            (client_id,)
        )
        row = cur.fetchone()
        return row["id"] if row else None
