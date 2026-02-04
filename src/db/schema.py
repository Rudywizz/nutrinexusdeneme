import sqlite3

SCHEMA_SQL = r'''
CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS client_kcal_targets (
  client_id TEXT PRIMARY KEY,
  target_kcal REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);


-- Danışanlar
CREATE TABLE IF NOT EXISTS clients (
  id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  birth_date TEXT NOT NULL,  -- YYYY-MM-DD
  gender TEXT NOT NULL,      -- Kadın/Erkek/Diğer
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_active ON clients(is_active);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(full_name);
CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone);

CREATE TABLE IF NOT EXISTS autosave_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,          -- client/measurement/clinical/food_card/diet_plan/lab_review
  entity_id TEXT,                      -- varsa
  client_id TEXT,                      -- varsa
  payload_json TEXT NOT NULL,          -- form state
  updated_at TEXT NOT NULL,            -- ISO datetime
  app_version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_autosave_updated_at ON autosave_drafts(updated_at);
CREATE INDEX IF NOT EXISTS idx_autosave_entity ON autosave_drafts(entity_type, entity_id);

-- Klinik profil (Anamnez vb.) - danışan başına tek kayıt
CREATE TABLE IF NOT EXISTS clinical_profiles (
  client_id TEXT PRIMARY KEY,
  diseases TEXT NOT NULL DEFAULT '',
  allergies TEXT NOT NULL DEFAULT '',
  intolerances TEXT NOT NULL DEFAULT '',
  medications TEXT NOT NULL DEFAULT '',
  supplements TEXT NOT NULL DEFAULT '',
  lifestyle TEXT NOT NULL DEFAULT '',
  activity_level TEXT NOT NULL DEFAULT '',
  sleep TEXT NOT NULL DEFAULT '',
  stress TEXT NOT NULL DEFAULT '',
  smoking TEXT NOT NULL DEFAULT '',
  alcohol TEXT NOT NULL DEFAULT '',
  water TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);



-- Kan tahlili importları (PDF yüklemeleri)
CREATE TABLE IF NOT EXISTS lab_imports (
  id TEXT PRIMARY KEY,                 -- UUID
  client_id TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  source_path TEXT NOT NULL,
  imported_at TEXT NOT NULL,           -- ISO datetime
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lab_imports_client ON lab_imports(client_id, imported_at);

-- Kan tahlili sonuçları (satır bazlı)
CREATE TABLE IF NOT EXISTS lab_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_id TEXT NOT NULL,
  client_id TEXT NOT NULL,
  taken_at TEXT NOT NULL,              -- ISO datetime (rapordaki tarih/saat varsa), yoksa imported_at
  test_name TEXT NOT NULL,
  result_text TEXT NOT NULL,
  result_value REAL,                   -- parse edilebildiyse
  unit TEXT NOT NULL DEFAULT '',
  ref_text TEXT NOT NULL DEFAULT '',
  ref_low REAL,
  ref_high REAL,
  ref_mode TEXT NOT NULL DEFAULT 'unknown',  -- range/lt/gt/unknown
  status TEXT NOT NULL DEFAULT 'unknown',    -- low/high/normal/borderline/unknown
  created_at TEXT NOT NULL,
  FOREIGN KEY(import_id) REFERENCES lab_imports(id) ON DELETE CASCADE,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lab_results_client ON lab_results(client_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_lab_results_import ON lab_results(import_id);




-- Besin tüketimi (Sprint-4.7)
CREATE TABLE IF NOT EXISTS foods_catalog_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foods_catalog (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kcal_per_100g REAL NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_foods_catalog_name ON foods_catalog(name);

CREATE TABLE IF NOT EXISTS food_consumption_entries (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  entry_date TEXT NOT NULL,         -- YYYY-MM-DD
  meal_type TEXT NOT NULL DEFAULT '',
  food_name TEXT NOT NULL DEFAULT '',
  amount_g REAL NOT NULL DEFAULT 0,
  kcal_per_100g REAL NOT NULL DEFAULT 0,
  kcal_total REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_food_entries_client_date ON food_consumption_entries(client_id, entry_date);

CREATE TABLE IF NOT EXISTS foods_favorites (
  client_id TEXT NOT NULL,
  food_name TEXT NOT NULL,
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (client_id, food_name),
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meal_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  items_json TEXT NOT NULL DEFAULT '[]', -- [{meal_type, food_name, amount_g}]
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meal_templates_name ON meal_templates(name);


-- Randevular (Sprint 6.0)
CREATE TABLE IF NOT EXISTS appointments (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  starts_at TEXT NOT NULL,            -- ISO datetime: YYYY-MM-DD HH:MM:SS
  duration_min INTEGER NOT NULL DEFAULT 30,
  title TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Planlandı',  -- Planlandı/Tamamlandı/İptal
  notified INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_appointments_client_date ON appointments(client_id, starts_at);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status, starts_at);

-- Ölçümler (danışan bazlı, çoklu kayıt)

-- Danışan Dosyaları (ekler)
CREATE TABLE IF NOT EXISTS client_files (
  id TEXT PRIMARY KEY,                 -- UUID
  client_id TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Diğer',  -- Tahlil/Diyet/Fotoğraf/Rapor/Diğer
  title TEXT NOT NULL DEFAULT '',
  orig_name TEXT NOT NULL,
  stored_path TEXT NOT NULL,           -- tam dosya yolu
  note TEXT NOT NULL DEFAULT '',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_client_files_client ON client_files(client_id, created_at);



-- Diyet Planları
CREATE TABLE IF NOT EXISTS diet_plans (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  title TEXT NOT NULL,
  start_date TEXT NOT NULL, -- YYYY-MM-DD
  end_date TEXT NOT NULL DEFAULT '',
  plan_text TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  is_active_plan INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_diet_plans_client ON diet_plans(client_id, start_date);

CREATE TABLE IF NOT EXISTS measurements (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL,
  measured_at TEXT NOT NULL,           -- YYYY-MM-DD
  height_cm REAL,                      -- opsiyonel
  weight_kg REAL,
  waist_cm REAL,
  hip_cm REAL,
  neck_cm REAL,
  body_fat_percent REAL,
  muscle_kg REAL,
  water_percent REAL,
  visceral_fat REAL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_measurements_client_date ON measurements(client_id, measured_at);


-- Şablonlar (Sprint 6.1.0)
CREATE TABLE IF NOT EXISTS food_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  food_name TEXT NOT NULL DEFAULT '',
  amount REAL NOT NULL DEFAULT 0,
  unit TEXT NOT NULL DEFAULT 'g',
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS meal_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1
);
'''


from pathlib import Path

def seed_tr_core_curated(conn: sqlite3.Connection) -> None:
    """Force-apply Kurumsal TR çekirdek katalog to foods_curated.

    This is a deterministic, offline seed from an embedded CSV file.
    It wipes foods_curated to guarantee a clean, Turkish-only catalog.
    """
    from pathlib import Path
    import csv
    from datetime import datetime

    # Ensure table exists
    conn.execute("""
    CREATE TABLE IF NOT EXISTS foods_curated (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      kcal_per_100g REAL NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      category TEXT NOT NULL
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS foods_catalog_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    """)

    csv_path = Path(__file__).resolve().parents[1] / "assets" / "data" / "kurumsal_tr_cekirdek_catalog.csv"
    if not csv_path.exists():
        return

    conn.execute("DELETE FROM foods_curated")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            cat = (row.get("category") or "").strip()
            kcal = row.get("kcal_per_100g") or "0"
            if not name or not cat:
                continue
            try:
                kcal_val = float(kcal)
            except Exception:
                kcal_val = 0.0
            food_id = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            conn.execute(
                """INSERT INTO foods_curated (id,name,kcal_per_100g,is_active,created_at,updated_at,category)
                VALUES (?,?,?,?,?,?,?)""",
                (food_id, name, kcal_val, 1, now, now, cat),
            )

    conn.execute("INSERT OR REPLACE INTO foods_catalog_meta (key,value) VALUES ('catalog_source','Kurumsal TR Çekirdek')")
    conn.execute("INSERT OR REPLACE INTO foods_catalog_meta (key,value) VALUES ('catalog_version','v2-tr-core')")

def seed_foods_catalog(conn: sqlite3.Connection) -> None:
    """Seed foods_catalog from embedded base DB if catalog is empty.

    This avoids runtime CSV imports (freeze risk) and guarantees thousands of foods
    are available out-of-the-box offline.
    """
    try:
        cur = conn.execute("SELECT COUNT(1) AS c FROM foods_catalog")
        c = int(cur.fetchone()[0] or 0)
    except Exception:
        # Table may not exist yet; ensure_schema creates it first.
        return

    if c > 0:
        return

    # Embedded base DB path: src/assets/data/foods_base.db
    base_db = Path(__file__).resolve().parents[1] / "assets" / "data" / "foods_base.db"
    if not base_db.exists():
        return

    # IMPORTANT: SQLite cannot DETACH within an open transaction.
    # When we copy from the attached DB, sqlite3 implicitly opens a transaction
    # for the INSERTs. If we try to DETACH before COMMIT, SQLite raises:
    #   sqlite3.OperationalError: database base is locked
    # So we commit before detaching, and always attempt to detach in finally.
    attached = False
    try:
        conn.execute("ATTACH DATABASE ? AS base", (str(base_db),))
        attached = True

        # Copy foods and meta
        conn.execute(
            "INSERT OR REPLACE INTO foods_catalog(id,name,kcal_per_100g,is_active,created_at,updated_at) "
            "SELECT id,name,kcal_per_100g,is_active,created_at,updated_at FROM base.foods_catalog"
        )
        try:
            conn.execute(
                "INSERT OR REPLACE INTO foods_catalog_meta(key,value) "
                "SELECT key,value FROM base.foods_catalog_meta"
            )
        except Exception:
            pass

        # End implicit transaction BEFORE detaching.
        conn.commit()
    finally:
        if attached:
            try:
                conn.execute("DETACH DATABASE base")
            except Exception:
                # If detach fails, keep going; the main connection will close on exit.
                pass

def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)

    # --- Lightweight, backwards-compatible migrations ---
    # SQLite doesn't support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
    # so we probe PRAGMA table_info and add missing columns when needed.
    def _has_column(table: str, column: str) -> bool:
        try:
            cur = conn.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]  # (cid, name, type, notnull, dflt_value, pk)
            return column in cols
        except Exception:
            return False

    def _add_column(table: str, ddl_fragment: str) -> None:
        # ddl_fragment example: "plan_text TEXT NOT NULL DEFAULT ''"
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl_fragment}")

    
    # Sprint 5.0 - Besin Tüketimi: satır sırası için display_order
    if not _has_column('food_consumption_entries', 'display_order'):
        _add_column('food_consumption_entries', 'display_order INTEGER NOT NULL DEFAULT 0')

# Sprint 4.6 introduced diet_plans.plan_text. If the user DB was created
    # on an earlier build, the column won't exist and will crash queries.
    if not _has_column('diet_plans', 'plan_text'):
        _add_column('diet_plans', "plan_text TEXT NOT NULL DEFAULT ''")

    # Sprint 4.6/4.7 introduced diet_plans.is_active_plan to mark the currently
    # active plan. Older DBs won't have this column.
    if not _has_column('diet_plans', 'is_active_plan'):
        _add_column('diet_plans', 'is_active_plan INTEGER NOT NULL DEFAULT 0')

    
    # Appointments: add notification flag for in-app reminders (Sprint 6.0.1)
    if not _has_column('appointments', 'notified'):
        _add_column('appointments', 'notified INTEGER NOT NULL DEFAULT 0')

# Some early DBs had diet_plans without the soft-delete flag.
    # Current code filters by is_active=1, so missing column will crash.
    if not _has_column('diet_plans', 'is_active'):
        _add_column('diet_plans', 'is_active INTEGER NOT NULL DEFAULT 1')


    
    # Sprint 6.0.4 - Appointments: optional phone field
    if not _has_column('appointments', 'phone'):
        _add_column('appointments', "phone TEXT NOT NULL DEFAULT ''")

# Seed embedded foods catalog (Sprint 4.9.5)

    # Sprint 6.1.0 - Templates: ensure meal_templates has content/updated_at columns (back-compat)
    if not _has_column('meal_templates', 'content'):
        _add_column('meal_templates', "content TEXT NOT NULL DEFAULT ''")
        # If older schema had items_json, preserve it into content as a fallback
        if _has_column('meal_templates', 'items_json'):
            try:
                conn.execute("UPDATE meal_templates SET content=items_json WHERE (content='' OR content IS NULL) AND (items_json IS NOT NULL AND items_json!='')")
            except Exception:
                pass

    if not _has_column('meal_templates', 'updated_at'):
        _add_column('meal_templates', "updated_at TEXT NOT NULL DEFAULT ''")
        try:
            conn.execute("UPDATE meal_templates SET updated_at=created_at WHERE (updated_at='' OR updated_at IS NULL) AND (created_at IS NOT NULL AND created_at!='')")
        except Exception:
            pass

    seed_foods_catalog(conn)
    seed_tr_core_curated(conn)

    conn.commit()