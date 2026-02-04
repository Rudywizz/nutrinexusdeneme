import sqlite3
from pathlib import Path

def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Dayanıklılık ayarları (elektrik kesintisi/çökme senaryosu)
    # WAL: daha güvenli + performans iyi
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=FULL;")  # güvenlik > performans
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
