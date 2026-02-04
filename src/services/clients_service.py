from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from src.app.utils.dates import format_tr_date


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass
class Client:
    id: str
    full_name: str
    phone: str
    birth_date: str  # YYYY-MM-DD
    gender: str
    is_active: int = 1

    # Eski DB sürümlerinde bu kolonlar olmayabilir. Varsayılan veriyoruz.
    created_at: str = ""
    updated_at: str = ""

    def to_ui_dict(self) -> dict:
        # UI için doğum tarihini TR formatında gösterelim (DB'de ISO YYYY-MM-DD tutulur).
        dob_iso = self.birth_date or ""
        dob_display = format_tr_date(dob_iso) if dob_iso else ""
        return {
            "id": self.id,
            "name": self.full_name,
            "phone": self.phone,
            "birth_date": dob_iso,   # form/dialog için ISO
            "dob": dob_display,      # ekranda görünen
            "gender": self.gender,
            "is_active": bool(self.is_active),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

class ClientsService:
    """Sprint-1: Danışan CRUD."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # DB şemasını sürümler arası uyumlu yönetmek için kolonları keşfediyoruz.
        try:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(clients)").fetchall()}
        except Exception:
            cols = set()
        self._has_created_at = "created_at" in cols
        self._has_updated_at = "updated_at" in cols

    def list_clients(self, *, only_active: bool = True, query: str | None = None) -> list[Client]:
        q = (query or "").strip().lower()
        where = []
        params: list[object] = []
        if only_active:
            where.append("is_active = 1")
        if q:
            where.append("(lower(full_name) LIKE ? OR phone LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sql = (
            "SELECT id, full_name, phone, birth_date, gender, is_active "
            "FROM clients" + where_sql + " ORDER BY full_name COLLATE NOCASE"
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [Client(**dict(r)) for r in rows]

    def get_client(self, client_id: str) -> Optional[Client]:
        row = self.conn.execute(
            "SELECT id, full_name, phone, birth_date, gender, is_active FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
        return Client(**dict(row)) if row else None

    def create_client(self, *, full_name: str, phone: str, birth_date: str, gender: str) -> Client:
        cid = str(uuid4())
        now = _now_iso()
        if self._has_created_at and self._has_updated_at:
            self.conn.execute(
                "INSERT INTO clients(id, full_name, phone, birth_date, gender, is_active, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, 1, ?, ?)",
                (cid, full_name.strip(), phone.strip(), birth_date.strip(), gender.strip(), now, now),
            )
        else:
            # Eski şema (created_at/updated_at yok)
            self.conn.execute(
                "INSERT INTO clients(id, full_name, phone, birth_date, gender, is_active) "
                "VALUES(?, ?, ?, ?, ?, 1)",
                (cid, full_name.strip(), phone.strip(), birth_date.strip(), gender.strip()),
            )
        self.conn.commit()
        return Client(id=cid, full_name=full_name.strip(), phone=phone.strip(), birth_date=birth_date.strip(), gender=gender.strip(), is_active=1)

    def update_client(self, client_id: str, *, full_name: str, phone: str, birth_date: str, gender: str) -> Client:
        now = _now_iso()
        if self._has_updated_at:
            self.conn.execute(
                "UPDATE clients SET full_name=?, phone=?, birth_date=?, gender=?, updated_at=? WHERE id=?",
                (full_name.strip(), phone.strip(), birth_date.strip(), gender.strip(), now, client_id),
            )
        else:
            self.conn.execute(
                "UPDATE clients SET full_name=?, phone=?, birth_date=?, gender=? WHERE id=?",
                (full_name.strip(), phone.strip(), birth_date.strip(), gender.strip(), client_id),
            )
        self.conn.commit()
        c = self.get_client(client_id)
        if not c:
            raise RuntimeError("Danışan bulunamadı")
        return c

    def deactivate_client(self, client_id: str) -> None:
        now = _now_iso()
        if self._has_updated_at:
            self.conn.execute("UPDATE clients SET is_active=0, updated_at=? WHERE id=?", (now, client_id))
        else:
            self.conn.execute("UPDATE clients SET is_active=0 WHERE id=?", (client_id,))
        self.conn.commit()