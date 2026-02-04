
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional, Iterable


@dataclass
class FoodConsumptionEntry:
    id: str
    client_id: str
    entry_date: str          # YYYY-MM-DD
    meal_type: str
    food_name: str
    amount_g: float
    kcal_per_100g: float
    kcal_total: float
    note: str
    created_at: str
    updated_at: str


class FoodConsumptionService:
    """
    Offline-first Besin Tüketimi servis katmanı.
    - entries: danışan + gün bazlı kayıtlar
    - foods_catalog: mini besin kataloğu (kcal/100g)
    - templates: öğün şablonları (JSON item list)
    - favorites: danışan bazlı sık kullanılanlar (otomatik güncellenir)
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # In-memory catalog cache for fast autocomplete (prevents UI lag on typing)
        self._catalog_names_cache: list[str] | None = None
        self._catalog_names_cache_norm: list[str] | None = None

    def _has_base_catalog(self) -> bool:
        try:
            rows = self.conn.execute("PRAGMA database_list").fetchall()
            return any(r[1] == "base" for r in rows)
        except Exception:
            return False

    def _catalog_table(self) -> str:
        # Embedded base DB is used only for initial seeding.
        # Runtime reads should use the main table so user updates (CSV/URL) work.
        return "foods_curated"

    def _load_catalog_cache(self) -> None:
        """Load active catalog names into memory once for fast suggestion filtering."""
        if self._catalog_names_cache is not None:
            return
        try:
            rows = self.conn.execute(
                f"""SELECT name FROM {self._catalog_table()} WHERE is_active=1"""
            ).fetchall()
            # sqlite3.Row supports mapping access via ["col"], but not dict.get()
            names = [r["name"] for r in rows if r and r["name"]]
        except Exception:
            names = []
        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        self._catalog_names_cache = sorted(uniq, key=lambda s: s.casefold())
        # Precompute casefolded strings for fast 'contains' checks (Turkish-safe enough for UI search)
        self._catalog_names_cache_norm = [n.casefold() for n in self._catalog_names_cache]

    def invalidate_catalog_cache(self) -> None:
        """Call when catalog is updated to refresh autocomplete cache."""
        self._catalog_names_cache = None
        self._catalog_names_cache_norm = None

    # ---------- Calculations (single source of truth) ----------
    @staticmethod
    def calc_kcal_total(amount_g: float, kcal_per_100g: float) -> float:
        """Calculate kcal total for a given gram amount and kcal/100g value."""
        try:
            g = float(amount_g or 0)
            k = float(kcal_per_100g or 0)
            return (g * k) / 100.0 if g and k else 0.0
        except Exception:
            return 0.0

    def compute_meal_totals(self, rows: list[dict]) -> tuple[dict[str, float], float]:
        """Compute meal subtotals and daily total from UI rows.

        rows: [{meal_type, amount_g, kcal_per_100g}] or [{meal_type, kcal_total}]
        """
        meal_totals: dict[str, float] = {}
        total = 0.0
        for r in rows or []:
            meal = (r.get("meal_type") or "").strip() or "Diğer"
            if "kcal_total" in r and r.get("kcal_total") is not None:
                kcal = float(r.get("kcal_total") or 0)
            else:
                kcal = self.calc_kcal_total(r.get("amount_g", 0), r.get("kcal_per_100g", 0))
            meal_totals[meal] = meal_totals.get(meal, 0.0) + kcal
            total += kcal
        return meal_totals, total

    # ---------- Seed / meta ----------
    def ensure_seed_catalog(self) -> None:
        # Mini, pratik bir başlangıç kataloğu (kullanıcı isterse internetten güncelleyebilecek)
        cur = self.conn.execute("SELECT COUNT(1) AS c FROM foods_catalog")
        c = int(cur.fetchone()["c"])
        if c > 0:
            return

        seed = [
            ("Yumurta (tam)", 143.0),
            ("Yumurta (beyaz)", 52.0),
            ("Peynir (beyaz)", 260.0),
            ("Zeytin", 145.0),
            ("Bal", 304.0),
            ("Reçel", 278.0),
            ("Ekmek (beyaz)", 265.0),
            ("Ekmek (tam buğday)", 247.0),
            ("Yulaf", 389.0),
            ("Süt (yarım yağlı)", 50.0),
            ("Yoğurt", 61.0),
            ("Ayran", 36.0),
            ("Tavuk göğüs", 165.0),
            ("Hindi göğüs", 135.0),
            ("Kırmızı et (yağsız)", 195.0),
            ("Somon", 208.0),
            ("Ton balığı", 132.0),
            ("Pirinç (pişmiş)", 130.0),
            ("Bulgur (pişmiş)", 83.0),
            ("Makarna (pişmiş)", 158.0),
            ("Patates (haşlanmış)", 87.0),
            ("Muz", 89.0),
            ("Elma", 52.0),
            ("Portakal", 47.0),
            ("Çilek", 32.0),
            ("Badem", 579.0),
            ("Ceviz", 654.0),
            ("Fındık", 628.0),
            ("Zeytinyağı", 884.0),
            ("Şeker", 387.0),
        ]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.executemany(
            "INSERT INTO foods_catalog (id, name, kcal_per_100g, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
            [(str(uuid.uuid4()), n, k, now, now) for (n, k) in seed],
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    # ---------- Catalog ----------
    def search_catalog(self, prefix: str, limit: int = 20) -> list[dict]:
        prefix = (prefix or "").strip()
        if not prefix:
            rows = self.conn.execute(
                "SELECT name, kcal_per_100g FROM {t} WHERE is_active=1 ORDER BY name COLLATE NOCASE LIMIT ?".format(t=self._catalog_table()),
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT name, kcal_per_100g FROM {t} WHERE is_active=1 AND name LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?".format(t=self._catalog_table()),
                (prefix + "%", limit),
            ).fetchall()
        return [{"name": r["name"], "kcal_per_100g": float(r["kcal_per_100g"] or 0)} for r in rows]

    def get_catalog_item(self, name: str) -> Optional[dict]:
        if not name:
            return None
        row = self.conn.execute(
            f"SELECT name, kcal_per_100g FROM {self._catalog_table()} WHERE is_active=1 AND lower(name)=lower(?) LIMIT 1",
            (name.strip(),),
        ).fetchone()
        if not row:
            return None
        return {"name": row["name"], "kcal_per_100g": float(row["kcal_per_100g"] or 0)}

    def replace_catalog(self, items: Iterable[tuple[str, float]]) -> int:
        """Replace catalog with given items (name, kcal_per_100g). Returns inserted count."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("DELETE FROM foods_catalog")
        self.conn.executemany(
            "INSERT INTO foods_catalog (id, name, kcal_per_100g, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
            [(str(uuid.uuid4()), n.strip(), float(k), now, now) for (n, k) in items if n and str(n).strip()],
        )
        self.conn.commit()
        cur = self.conn.execute("SELECT COUNT(1) AS c FROM foods_catalog")
        return int(cur.fetchone()["c"])

    # ---------- Entries ----------
    def list_entries(self, client_id: str, entry_date: str) -> list[FoodConsumptionEntry]:
        # IMPORTANT: Keep UI order stable.
        # Alphabetical ORDER BY meal_type causes meals like "Akşam" to jump above "Kahvaltı" after save.
        # We therefore use a deterministic meal rank (custom order) + created_at for within-meal order.
        rows = self.conn.execute(
            """SELECT id, client_id, entry_date, meal_type, food_name, amount_g, kcal_per_100g, kcal_total, note, created_at, updated_at
               FROM food_consumption_entries
               WHERE client_id=? AND entry_date=?
               ORDER BY
                 CASE
                   WHEN display_order IS NOT NULL AND display_order > 0 THEN display_order
                   ELSE
                     CASE meal_type
                       WHEN 'Kahvaltı' THEN 10001
                       WHEN 'Ara Öğün 1' THEN 10002
                       WHEN 'Öğle' THEN 10003
                       WHEN 'Ara Öğün 2' THEN 10004
                       WHEN 'Akşam' THEN 10005
                       WHEN 'Gece' THEN 10006
                       ELSE 19999
                     END
                 END,
                 created_at""",
            (client_id, entry_date),
        ).fetchall()
        return [FoodConsumptionEntry(*row) for row in rows]

    def upsert_entry(
        self,
        *,
        entry_id: Optional[str],
        client_id: str,
        entry_date: str,
        meal_type: str,
        food_name: str,
        amount_g: float,
        kcal_per_100g: float,
        note: str = "",
        display_order: int = 0,
    ) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        amount_g = float(amount_g or 0)
        kcal_per_100g = float(kcal_per_100g or 0)
        kcal_total = (amount_g * kcal_per_100g) / 100.0 if amount_g and kcal_per_100g else 0.0

        if entry_id:
            self.conn.execute(
                """UPDATE food_consumption_entries
                   SET meal_type=?, food_name=?, amount_g=?, kcal_per_100g=?, kcal_total=?, note=?, display_order=?, updated_at=?
                   WHERE id=? AND client_id=?""",
                (meal_type, food_name, amount_g, kcal_per_100g, kcal_total, note, int(display_order or 0), now, entry_id, client_id),
            )
        else:
            entry_id = str(uuid.uuid4())
            self.conn.execute(
                """INSERT INTO food_consumption_entries
                   (id, client_id, entry_date, meal_type, food_name, amount_g, kcal_per_100g, kcal_total, note, display_order, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, client_id, entry_date, meal_type, food_name, amount_g, kcal_per_100g, kcal_total, note, int(display_order or 0), now, now),
            )

        # favorites upsert (very light)
        if food_name and food_name.strip():
            self.conn.execute(
                """INSERT INTO foods_favorites (client_id, food_name, use_count, last_used_at)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(client_id, food_name) DO UPDATE SET
                     use_count = use_count + 1,
                     last_used_at = excluded.last_used_at""",
                (client_id, food_name.strip(), now),
            )

        self.conn.commit()
        return entry_id

    def delete_entry(self, client_id: str, entry_id: str) -> None:
        self.conn.execute("DELETE FROM food_consumption_entries WHERE id=? AND client_id=?", (entry_id, client_id))
        self.conn.commit()

    def delete_day(self, client_id: str, entry_date: str) -> None:
        self.conn.execute("DELETE FROM food_consumption_entries WHERE client_id=? AND entry_date=?", (client_id, entry_date))
        self.conn.commit()

    def copy_day(self, client_id: str, from_date: str, to_date: str) -> int:
        """Copy entries from from_date to to_date. Replaces destination day. Returns copied count."""
        src = self.list_entries(client_id, from_date)
        self.delete_day(client_id, to_date)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for e in src:
            new_id = str(uuid.uuid4())
            rows.append((new_id, client_id, to_date, e.meal_type, e.food_name, float(e.amount_g or 0), float(e.kcal_per_100g or 0),
                         float(e.kcal_total or 0), e.note or "", now, now))
        if rows:
            self.conn.executemany(
                """INSERT INTO food_consumption_entries
                   (id, client_id, entry_date, meal_type, food_name, amount_g, kcal_per_100g, kcal_total, note, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            self.conn.commit()
        return len(rows)

    # ---------- Suggestions ----------
    def get_suggestions(self, client_id: str, prefix: str, limit: int = 25) -> list[str]:
        """
        Autocomplete suggestions:
        1) danışan favorileri (use_count desc)
        2) güncel catalog (name asc)
        3) son 30 günden entry'ler
        """
        p = (prefix or "").strip()
        like = p + "%" if p else "%"
        res: list[str] = []

        fav_rows = self.conn.execute(
            """SELECT food_name FROM foods_favorites
               WHERE client_id=? AND food_name LIKE ?
               ORDER BY use_count DESC, last_used_at DESC
               LIMIT ?""",
            (client_id, like, limit),
        ).fetchall()
        for r in fav_rows:
            n = r["food_name"]
            if n and n not in res:
                res.append(n)

        if len(res) < limit:
            # Catalog suggestions (in-memory cache to keep UI snappy)
            self._load_catalog_cache()
            cache = self._catalog_names_cache or []
            cache_norm = self._catalog_names_cache_norm or []
            if p:
                needle = p.casefold()
                for name, n_norm in zip(cache, cache_norm):
                    if needle in n_norm and name not in res:
                        res.append(name)
                        if len(res) >= limit:
                            break
            else:
                for name in cache:
                    if name not in res:
                        res.append(name)
                        if len(res) >= limit:
                            break

        if len(res) < limit:
            # recent entries
            # last 30 days window
            try:
                d = datetime.strptime(date.today().strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            except Exception:
                d = date.today()
            start = (d - timedelta(days=30)).strftime("%Y-%m-%d")
            rows = self.conn.execute(
                """SELECT DISTINCT food_name FROM food_consumption_entries
                   WHERE client_id=? AND entry_date>=? AND food_name LIKE ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (client_id, start, like, limit),
            ).fetchall()
            for r in rows:
                n = r["food_name"]
                if n and n not in res:
                    res.append(n)
                if len(res) >= limit:
                    break

        return res[:limit]

    # ---------- Templates ----------
    def list_templates(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, items_json, created_at FROM meal_templates WHERE is_active=1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        out = []
        for r in rows:
            items = []
            try:
                items = json.loads(r["items_json"] or "[]")
            except Exception:
                items = []
            out.append({"id": r["id"], "name": r["name"], "items": items, "created_at": r["created_at"]})
        return out

    def create_template(self, name: str, items: list[dict]) -> str:
        tid = str(uuid.uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO meal_templates (id, name, items_json, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (tid, name.strip(), json.dumps(items, ensure_ascii=False), now),
        )
        self.conn.commit()
        return tid

    def deactivate_template(self, template_id: str) -> None:
        self.conn.execute("UPDATE meal_templates SET is_active=0 WHERE id=?", (template_id,))
        self.conn.commit()

    # ---------- Plan target kcal (client-specific) ----------
    def get_target_kcal(self, client_id: str) -> Optional[float]:
        """Return stored daily target kcal for a client (or None if not set)."""
        try:
            row = self.conn.execute(
                "SELECT target_kcal FROM client_kcal_targets WHERE client_id=?",
                (client_id,),
            ).fetchone()
            if not row:
                return None
            val = float(row[0] or 0)
            return val if val > 0 else None
        except Exception:
            return None

    def set_target_kcal(self, client_id: str, target_kcal: float) -> None:
        """Upsert daily target kcal for a client."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT OR REPLACE INTO client_kcal_targets(client_id, target_kcal, updated_at) VALUES (?,?,?)",
            (client_id, float(target_kcal or 0), now),
        )
        self.conn.commit()

