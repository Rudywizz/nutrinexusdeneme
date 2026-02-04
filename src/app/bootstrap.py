from pathlib import Path
from src.services.backup import resolve_backup_root
from src.services.logger import setup_logger
from src.db.connection import connect_sqlite
from src.db.schema import ensure_schema
from src.app.state import AppState

def _attach_base_catalog(conn, base_db_path: Path, log):
    # Attach as read-mostly catalog DB for fast search without copying into main DB.
    # We intentionally avoid any writes to this attached DB.
    if not base_db_path.exists():
        log.warning("foods_base.db not found at %s (catalog features may be limited)", base_db_path)
        return
    try:
        # If already attached, skip
        rows = conn.execute("PRAGMA database_list").fetchall()
        if any(r[1] == "base" for r in rows):
            return
        p = str(base_db_path).replace("'", "''")
        conn.execute(f"ATTACH DATABASE '{p}' AS base")
    except Exception as e:
        log.warning("Failed to ATTACH base catalog: %s", e)

def bootstrap() -> tuple[AppState, object]:
    backup_root = resolve_backup_root()
    log = setup_logger(backup_root / "logs")

    db_path = backup_root / "nutrinexus.db"
    conn = connect_sqlite(db_path)
    ensure_schema(conn)

    # Resolve embedded base catalog path (src/assets/data/foods_base.db)
    src_root = Path(__file__).resolve().parents[1]  # .../src
    foods_base_db_path = src_root / "assets" / "data" / "foods_base.db"
    _attach_base_catalog(conn, foods_base_db_path, log)

    log.info("Backup root: %s", backup_root)
    log.info("DB path: %s", db_path)

    state = AppState(backup_root=backup_root, db_path=db_path, conn=conn, foods_base_db_path=foods_base_db_path)
    return state, log
