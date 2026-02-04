import sqlite3
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from typing import List, Optional, Dict, Any


@dataclass
class FoodTemplate:
    id: str
    name: str
    food_name: str
    amount: float
    unit: str
    note: str
    updated_at: str


@dataclass
class MealTemplate:
    id: str
    name: str
    content: str
    updated_at: str


class TemplatesService:
    def __init__(self, conn: sqlite3.Connection, log=None):
        self.conn = conn
        self.log = log


    # ---------- Foods Catalog (for autocomplete) ----------
    
    def list_catalog_food_names(self, q: str = "") -> List[str]:
        """Returns active catalog food names (Turkish curated first).

        NutriNexus uses **foods_curated** as the single source of truth (TR core seed).
        Older DBs may still have **foods_catalog**. We prefer foods_curated when present.
        """
        q = (q or "").strip()

        def _table_exists(table: str) -> bool:
            try:
                row = self.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                return bool(row)
            except Exception:
                return False

        table = "foods_curated" if _table_exists("foods_curated") else "foods_catalog"
        col = "name"

        if q:
            rows = self.conn.execute(
                f"""SELECT {col} AS name FROM {table}
                     WHERE is_active=1 AND {col} LIKE ?
                     ORDER BY {col} COLLATE NOCASE ASC""",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"""SELECT {col} AS name FROM {table}
                     WHERE is_active=1
                     ORDER BY {col} COLLATE NOCASE ASC"""
            ).fetchall()

        return [r["name"] for r in rows if (r["name"] or "").strip()]

    # ---------- Food Templates ----------
    def list_food_templates(self, q: str = "") -> List[FoodTemplate]:
        q = (q or "").strip()
        if q:
            rows = self.conn.execute(
                """SELECT id,name,food_name,amount,unit,note,updated_at
                     FROM food_templates
                     WHERE is_active=1 AND (name LIKE ? OR food_name LIKE ?)
                     ORDER BY updated_at DESC""",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT id,name,food_name,amount,unit,note,updated_at
                     FROM food_templates
                     WHERE is_active=1
                     ORDER BY updated_at DESC"""
            ).fetchall()
        return [
            FoodTemplate(
                id=r["id"], name=r["name"] or "", food_name=r["food_name"] or "",
                amount=float(r["amount"] or 0), unit=r["unit"] or "g",
                note=r["note"] or "", updated_at=r["updated_at"] or ""
            )
            for r in rows
        ]

    def upsert_food_template(self, *, tpl_id: Optional[str], name: str, food_name: str,
                             amount: float, unit: str, note: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = (name or "").strip()
        food_name = (food_name or "").strip()
        unit = (unit or "g").strip() or "g"
        note = (note or "").strip()

        if not name:
            raise ValueError("Şablon adı boş olamaz.")
        if amount is None:
            amount = 0
        try:
            amount = float(amount)
        except Exception:
            amount = 0.0

        if tpl_id:
            self.conn.execute(
                """UPDATE food_templates
                     SET name=?, food_name=?, amount=?, unit=?, note=?, updated_at=?
                     WHERE id=?""",
                (name, food_name, amount, unit, note, now, tpl_id),
            )
            self.conn.commit()
            return tpl_id

        tpl_id = uuid4().hex
        self.conn.execute(
            """INSERT INTO food_templates (id,name,food_name,amount,unit,note,created_at,updated_at,is_active)
                 VALUES (?,?,?,?,?,?,?,?,1)""",
            (tpl_id, name, food_name, amount, unit, note, now, now),
        )
        self.conn.commit()
        return tpl_id

    def delete_food_template(self, tpl_id: str) -> None:
        self.conn.execute(
            "UPDATE food_templates SET is_active=0 WHERE id=?",
            (tpl_id,),
        )
        self.conn.commit()

    # ---------- Meal Templates ----------
    def list_meal_templates(self, q: str = "") -> List[MealTemplate]:
        q = (q or "").strip()
        if q:
            rows = self.conn.execute(
                """SELECT id,name,content,updated_at
                     FROM meal_templates
                     WHERE is_active=1 AND (name LIKE ? OR content LIKE ?)
                     ORDER BY updated_at DESC""",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT id,name,content,updated_at
                     FROM meal_templates
                     WHERE is_active=1
                     ORDER BY updated_at DESC"""
            ).fetchall()
        return [
            MealTemplate(id=r["id"], name=r["name"] or "", content=r["content"] or "", updated_at=r["updated_at"] or "")
            for r in rows
        ]

    def upsert_meal_template(self, *, tpl_id: Optional[str], name: str, content: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = (name or "").strip()
        content = (content or "").strip()
        if not name:
            raise ValueError("Şablon adı boş olamaz.")

        if tpl_id:
            self.conn.execute(
                """UPDATE meal_templates
                     SET name=?, content=?, updated_at=?
                     WHERE id=?""",
                (name, content, now, tpl_id),
            )
            self.conn.commit()
            return tpl_id

        tpl_id = uuid4().hex
        self.conn.execute(
            """INSERT INTO meal_templates (id,name,content,created_at,updated_at,is_active)
                 VALUES (?,?,?,?,?,1)""",
            (tpl_id, name, content, now, now),
        )
        self.conn.commit()
        return tpl_id

    def delete_meal_template(self, tpl_id: str) -> None:
        self.conn.execute(
            "UPDATE meal_templates SET is_active=0 WHERE id=?",
            (tpl_id,),
        )
        self.conn.commit()
