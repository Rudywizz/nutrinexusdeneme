from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CatalogMeta:
    source_name: str = ""
    source_version: str = ""
    imported_at: str = ""
    file_hash: str = ""


class FoodsCatalogService:
    """Foods catalog service (Sprint 5 hotfix)

    **Single source of truth:** foods_curated

    This intentionally disables foods_catalog / embedded base DB / CSV runtime imports.
    The UI will only ever read from foods_curated, so what you write to DB is what you see.
    """

    TABLE = "foods_curated"
    META_TABLE = "foods_catalog_meta"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_tables()

    # ---------- schema ----------
    def _ensure_tables(self) -> None:
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE} (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kcal_per_100g REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            category TEXT NOT NULL
        )
        """)
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.META_TABLE} (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)

    # ---------- meta ----------
    def _meta_get(self, key: str, default: str = "") -> str:
        row = self.conn.execute(f"SELECT value FROM {self.META_TABLE} WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row and row[0] is not None else default

    def _meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            f"INSERT OR REPLACE INTO {self.META_TABLE} (key,value) VALUES (?,?)",
            (key, str(value)),
        )
        self.conn.commit()

    def get_meta(self) -> CatalogMeta:
        return CatalogMeta(
            source_name=self._meta_get("catalog_source", ""),
            source_version=self._meta_get("catalog_version", ""),
            imported_at=self._meta_get("imported_at", ""),
            file_hash=self._meta_get("file_hash", ""),
        )

    # ---------- core seed ----------
    def ensure_tr_core_seeded(self, csv_path: Path, force: bool = False, log=None) -> None:
        """Populate foods_curated from embedded TR core CSV.

        - If force=True: wipe & rewrite.
        - Else: only apply if current active count is very small (<150) or meta version not set.
        """
        try:
            current = int(self.conn.execute(f"SELECT COUNT(1) FROM {self.TABLE} WHERE is_active=1").fetchone()[0] or 0)
        except Exception:
            current = 0

        ver = self._meta_get("catalog_version", "")
        should_apply = force or (current < 150) or (ver.strip() == "")

        if not should_apply:
            return

        if not csv_path.exists():
            if log:
                log.error(f"TR core catalog CSV not found: {csv_path}")
            return

        # wipe
        self.conn.execute(f"DELETE FROM {self.TABLE}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip()
                cat = (row.get("category") or "").strip()
                kcal = row.get("kcal_per_100g") or row.get("kcal") or "0"
                if not name or not cat:
                    continue
                try:
                    kcal_val = float(kcal)
                except Exception:
                    kcal_val = 0.0

                # deterministic-ish id
                food_id = self.conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
                self.conn.execute(
                    f"""INSERT INTO {self.TABLE}
                    (id,name,kcal_per_100g,is_active,created_at,updated_at,category)
                    VALUES (?,?,?,?,?,?,?)""",
                    (food_id, name, kcal_val, 1, now, now, cat),
                )
                inserted += 1

        self._meta_set("catalog_source", "Kurumsal TR Çekirdek")
        self._meta_set("catalog_version", "v2-tr-core")
        self._meta_set("imported_at", now)
        self._meta_set("file_hash", "tr-core-v2")
        self.conn.commit()
        if log:
            log.info(f"TR core catalog applied: {inserted} rows")

    # ---------- queries ----------
    def get_count(self) -> int:
        row = self.conn.execute(f"SELECT COUNT(1) FROM {self.TABLE} WHERE is_active=1").fetchone()
        return int(row[0] or 0)

    def search_page(self, query: str = "", category: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        params: list[Any] = []
        where = "WHERE is_active=1"
        if q:
            where += " AND name LIKE ?"
            params.append(f"%{q}%")
        if category:
            where += " AND category=?"
            params.append(category)

        sql = f"""
        SELECT id, name, kcal_per_100g, category
        FROM {self.TABLE}
        {where}
        ORDER BY category, name
        LIMIT ? OFFSET ?
        """
        params.extend([int(limit), int(offset)])

        rows = []
        for r in self.conn.execute(sql, params).fetchall():
            rows.append({"id": r[0], "name": r[1], "kcal_per_100g": r[2], "category": r[3]})
        return rows
