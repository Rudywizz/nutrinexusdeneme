from __future__ import annotations

def _row_get(row, key, default=""):
    """Safe getter for sqlite3.Row / dict-like objects."""
    try:
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)
    except Exception:
        return default


import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from src.app.utils.dates import format_tr_date

def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")

def _parse_iso_dt(s: str) -> datetime:
    # Stored as "YYYY-MM-DD HH:MM:SS" (or without seconds) — be forgiving.
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    # fallback
    return datetime.now().replace(microsecond=0)

@dataclass
class Appointment:
    id: str
    client_id: str
    starts_at: str
    duration_min: int = 30
    title: str = ""
    note: str = ""
    phone: str = ""
    status: str = "Planlandı"
    notified: int = 0
    is_active: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_ui_dict(self, client_name: str = "") -> dict:
        dt = _parse_iso_dt(self.starts_at)
        date_iso = dt.strftime("%Y-%m-%d")
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": client_name,
            "starts_at": self.starts_at,
            "date": format_tr_date(date_iso),
            "time": dt.strftime("%H:%M"),
            "duration_min": int(self.duration_min or 0),
            "title": self.title or "",
            "note": self.note or "",
            "phone": self.phone or "",
            "status": self.status or "Planlandı",
            "is_active": bool(self.is_active),
        }

class AppointmentsService:
    """Sprint 6.0: Randevularım (liste + CRUD)."""

    VALID_STATUS = ["Planlandı", "Tamamlandı", "İptal"]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_appointments(self, *, date_from: str, date_to: str, query: str = "") -> list[dict]:
        # date_from/date_to are YYYY-MM-DD. We filter by starts_at.
        q = (query or "").strip().lower()
        where = ["a.is_active = 1", "substr(a.starts_at,1,10) >= ?", "substr(a.starts_at,1,10) <= ?"]
        params: list[object] = [date_from, date_to]
        if q:
            where.append("(lower(c.full_name) LIKE ? OR lower(a.title) LIKE ? OR lower(a.note) LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        sql = (
            "SELECT a.id, a.client_id, a.starts_at, a.duration_min, a.title, a.note, a.phone, a.status, a.notified, a.is_active, a.created_at, a.updated_at, "
            "c.full_name AS client_name "
            "FROM appointments a "
            "JOIN clients c ON c.id = a.client_id "
            "WHERE " + " AND ".join(where) + " "
            "ORDER BY a.starts_at ASC"
        )
        rows = self.conn.execute(sql, params).fetchall()
        out: list[dict] = []
        for r in rows:
            ap = Appointment(
                id=r["id"], client_id=r["client_id"], starts_at=r["starts_at"],
                duration_min=int(r["duration_min"] or 0),
                title=r["title"] or "", note=r["note"] or "", phone=_row_get(r, "phone", "") or "",
                status=r["status"] or "Planlandı",
                is_active=int(r["is_active"] or 1),
                created_at=r["created_at"] or "", updated_at=r["updated_at"] or "",
            )
            out.append(ap.to_ui_dict(client_name=r["client_name"] or ""))
        return out

    def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        r = self.conn.execute(
            "SELECT id, client_id, starts_at, duration_min, title, note, phone, status, is_active, created_at, updated_at "
            "FROM appointments WHERE id=?",
            (appt_id,),
        ).fetchone()
        if not r:
            return None
        return Appointment(**dict(r))

    def create_appointment(
        self, *, client_id: str, starts_at: str, duration_min: int, title: str, note: str, phone: str, status: str
    ) -> Appointment:
        appt_id = str(uuid4())
        now = _now_iso()
        st = status if status in self.VALID_STATUS else "Planlandı"
        self.conn.execute(
            "INSERT INTO appointments(id, client_id, starts_at, duration_min, title, note, phone, status, notified, is_active, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (appt_id, client_id, starts_at, int(duration_min or 0), title.strip(), note.strip(), (phone or '').strip(), st, 0, 1, now, now),
        )
        self.conn.commit()
        ap = self.get_appointment(appt_id)
        if not ap:
            raise RuntimeError("Randevu oluşturulamadı.")
        return ap

    def update_appointment(
        self, appt_id: str, *, client_id: str, starts_at: str, duration_min: int, title: str, note: str, phone: str, status: str
    ) -> Appointment:
        now = _now_iso()
        st = status if status in self.VALID_STATUS else "Planlandı"
        # If the start time changes, reset notification flag so reminders can trigger again.
        old = self.get_appointment(appt_id)
        old_starts = (old.starts_at if old else None)
        new_starts = starts_at
        reset_notified = 1 if (old_starts and old_starts != new_starts) else 0

        self.conn.execute(
            "UPDATE appointments SET client_id=?, starts_at=?, duration_min=?, title=?, note=?, phone=?, status=?, notified=CASE WHEN ?=1 THEN 0 ELSE notified END, updated_at=? WHERE id=?",
            (client_id, new_starts, int(duration_min or 0), title.strip(), note.strip(), (phone or '').strip(), st, reset_notified, now, appt_id),
        )
        self.conn.commit()
        ap = self.get_appointment(appt_id)
        if not ap:
            raise RuntimeError("Randevu bulunamadı.")
        return ap

    def deactivate_appointment(self, appt_id: str) -> None:
        """Soft delete: keeps record but hides it from UI."""
        now = _now_iso()
        self.conn.execute("UPDATE appointments SET is_active=0, updated_at=? WHERE id=?", (now, appt_id))
        self.conn.commit()

    def deactivate_day(self, date_iso: str) -> int:
        """Soft delete all appointments on a given day (YYYY-MM-DD). Returns affected count."""
        date_iso = (date_iso or "").strip()
        if not date_iso:
            return 0
        now = _now_iso()
        cur = self.conn.execute(
            "UPDATE appointments SET is_active=0, updated_at=? WHERE is_active=1 AND substr(starts_at,1,10)=?",
            (now, date_iso),
        )
        self.conn.commit()
        try:
            return int(cur.rowcount or 0)
        except Exception:
            return 0

    def copy_day(self, *, from_date: str, to_date: str) -> int:
        """Copy all active appointments from from_date to to_date (both YYYY-MM-DD).
        Keeps times and details; creates new ids; resets notified to 0. Returns created count.
        """
        from_date = (from_date or "").strip()
        to_date = (to_date or "").strip()
        if not from_date or not to_date:
            return 0

        rows = self.conn.execute(
            "SELECT client_id, starts_at, duration_min, title, note, phone, status FROM appointments "
            "WHERE is_active=1 AND substr(starts_at,1,10)=? ORDER BY starts_at ASC",
            (from_date,),
        ).fetchall()

        created = 0
        now = _now_iso()
        for r in rows:
            # keep time part
            starts = (r["starts_at"] or "").strip()
            time_part = "00:00:00"
            if len(starts) >= 16:
                # starts_at like 'YYYY-MM-DD HH:MM[:SS]'
                time_part = starts[11:]
                if len(time_part) == 5:
                    time_part = time_part + ":00"
            new_starts = f"{to_date} {time_part}"
            appt_id = str(uuid4())
            st = (r["status"] or "Planlandı")
            if st not in self.VALID_STATUS:
                st = "Planlandı"
            self.conn.execute(
                "INSERT INTO appointments(id, client_id, starts_at, duration_min, title, note, phone, status, notified, is_active, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    appt_id,
                    r["client_id"],
                    new_starts,
                    int(r["duration_min"] or 0),
                    (r["title"] or ""),
                    (r["note"] or ""),
                    (_row_get(r, "phone", "") or ""),
                    st,
                    0,
                    1,
                    now,
                    now,
                ),
            )
            created += 1
        if created:
            self.conn.commit()
        return created
    
    def move_day(self, *, from_date: str, to_date: str) -> int:
        """Move (copy then delete source) all active appointments from from_date to to_date.
        Returns moved count. Source appointments are soft-deleted (is_active=0).
        """
        from_date = (from_date or "").strip()
        to_date = (to_date or "").strip()
        if not from_date or not to_date or from_date == to_date:
            return 0

        rows = self.conn.execute(
            "SELECT id, client_id, starts_at, duration_min, title, note, phone, status FROM appointments "
            "WHERE is_active=1 AND substr(starts_at,1,10)=? ORDER BY starts_at ASC",
            (from_date,),
        ).fetchall()

        if not rows:
            return 0

        moved = 0
        now = _now_iso()
        src_ids = []
        try:
            self.conn.execute("BEGIN")
            for r in rows:
                src_ids.append(r["id"])
                starts = (r["starts_at"] or "").strip()
                time_part = "00:00:00"
                if len(starts) >= 16:
                    time_part = starts[11:]
                    if len(time_part) == 5:
                        time_part = time_part + ":00"
                new_starts = f"{to_date} {time_part}"
                appt_id = str(uuid4())
                st = (r["status"] or "Planlandı")
                if st not in self.VALID_STATUS:
                    st = "Planlandı"
                self.conn.execute(
                    "INSERT INTO appointments(id, client_id, starts_at, duration_min, title, note, phone, status, notified, is_active, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        appt_id,
                        r["client_id"],
                        new_starts,
                        int(r["duration_min"] or 0),
                        (r["title"] or ""),
                        (r["note"] or ""),
                        (_row_get(r, "phone", "") or ""),
                        st,
                        0,
                        1,
                        now,
                        now,
                    ),
                )
                moved += 1

            # soft delete source
            if src_ids:
                q_marks = ",".join(["?"] * len(src_ids))
                self.conn.execute(
                    f"UPDATE appointments SET is_active=0, updated_at=? WHERE id IN ({q_marks})",
                    (now, *src_ids),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return moved


    def counts_by_day(self, *, year: int, month: int) -> dict[str, int]:
        """Return {YYYY-MM-DD: count} for the given month (active appointments only)."""
        ym = f"{year:04d}-{month:02d}"
        rows = self.conn.execute(
            """
            SELECT substr(starts_at,1,10) AS d, COUNT(*) AS cnt
            FROM appointments
            WHERE is_active=1 AND substr(starts_at,1,7)=?
            GROUP BY substr(starts_at,1,10)
            """,
            (ym,),
        ).fetchall()
        out: dict[str, int] = {}
        for r in rows:
            out[str(r["d"])] = int(r["cnt"] or 0)
        return out

    def tooltips_by_day(self, *, year: int, month: int, max_items: int = 5) -> dict[str, str]:
        """Return {YYYY-MM-DD: tooltip_text} for the given month.

        Tooltip shows first `max_items` appointments of that day:
        '09:00 — Ayşe Kaya • Kontrol'
        """
        ym = f"{year:04d}-{month:02d}"
        rows = self.conn.execute(
            """
            SELECT substr(a.starts_at,1,10) AS d,
                   substr(a.starts_at,12,5) AS t,
                   COALESCE(c.full_name,'') AS client_name,
                   COALESCE(a.title,'') AS title
            FROM appointments a
            LEFT JOIN clients c ON c.id = a.client_id
            WHERE a.is_active=1 AND substr(a.starts_at,1,7)=?
            ORDER BY a.starts_at ASC
            """,
            (ym,),
        ).fetchall()

        by_day: dict[str, list[str]] = {}
        for r in rows:
            d = str(r["d"])
            t = str(r["t"] or "")
            name = (r["client_name"] or "").strip()
            title = (r["title"] or "").strip()
            line = t
            if name:
                line += f" — {name}"
            if title:
                line += f" • {title}"
            by_day.setdefault(d, []).append(line)

        out: dict[str, str] = {}
        for d, items in by_day.items():
            head = items[: max_items]
            more = len(items) - len(head)
            text = "\n".join(head)
            if more > 0:
                text += f"\n+{more} randevu daha..."
            out[d] = text
        return out

    def due_appointments(self, *, window_sec: int = 60, minutes_before: int = 0) -> list[Appointment]:
        """Bildirim için "zamanı gelen" randevuları döndürür.

        minutes_before=0 ise randevu saatinde; 10 ise randevudan 10 dk önce bildirim.
        window_sec, kontrol aralığına göre (ör. 60 sn) tekrar bildirimleri azaltmak için kullanılır.

        Not: Bu fonksiyon notified=0 olanları seçer; bildirim gönderildikten sonra
        mark_notified(...) ile işaretlenmelidir.
        """

        # starts_at formatı: 'YYYY-MM-DD HH:MM:SS'
        now = datetime.now()
        target = now + timedelta(minutes=int(minutes_before or 0))
        end = target + timedelta(seconds=int(window_sec))

        rows = self.conn.execute(
            """
            SELECT a.id,
                   a.client_id,
                   substr(a.starts_at, 1, 10) AS date,
                   substr(a.starts_at, 12, 5) AS time,
                   a.duration_min,
                   a.title,
                   a.note,
                   a.status,
                   COALESCE(a.phone,'') AS phone,
                   COALESCE(c.full_name,'') AS client_name,
                   a.starts_at
            FROM appointments a
            LEFT JOIN clients c ON c.id = a.client_id
            WHERE a.is_active=1 AND a.notified=0
              AND datetime(a.starts_at) >= datetime(?)
              AND datetime(a.starts_at) <  datetime(?)
            ORDER BY a.starts_at ASC
            """,
            (target.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchall()

        out: list[Appointment] = []
        for r in rows:
            out.append(
                Appointment(
                    id=str(r["id"]),
                    client_id=str(r["client_id"] or ""),
                    date=str(r["date"] or ""),
                    time=str(r["time"] or ""),
                    duration=int(r["duration_min"] or 30),
                    title=str(r["title"] or ""),
                    note=str(r["note"] or ""),
                    status=str(r["status"] or "Planlandı"),
                    phone=str(r["phone"] or ""),
                    client_name=str(r["client_name"] or ""),
                )
            )
        return out

    def mark_notified(self, appt_id: str) -> None:
        self.conn.execute("UPDATE appointments SET notified=1, updated_at=? WHERE id=?", (_now_iso(), appt_id))
        self.conn.commit()
