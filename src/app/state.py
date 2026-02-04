from dataclasses import dataclass
import sqlite3
from pathlib import Path

@dataclass
class AppState:
    backup_root: Path
    db_path: Path
    conn: sqlite3.Connection
    foods_base_db_path: Path
