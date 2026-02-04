import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import uuid
from datetime import datetime

@dataclass
class ClientFile:
    id: str
    client_id: str
    category: str
    title: str
    orig_name: str
    stored_path: str
    note: str
    is_active: int
    created_at: str

class ClientFilesService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_files(self, client_id: str) -> list[ClientFile]:
        cur = self.conn.execute(
            """SELECT id, client_id, category, title, orig_name, stored_path, note, is_active, created_at
                 FROM client_files
                 WHERE client_id=? AND is_active=1
                 ORDER BY created_at DESC""",
            (client_id,),
        )
        rows = cur.fetchall()
        return [ClientFile(**dict(r)) for r in rows]

    def add_file(
        self,
        client_id: str,
        category: str,
        title: str,
        orig_name: str,
        stored_path: str,
        note: str = "",
    ) -> str:
        fid = str(uuid.uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """INSERT INTO client_files (id, client_id, category, title, orig_name, stored_path, note, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, client_id, category, title or "", orig_name, stored_path, note or "", now),
        )
        self.conn.commit()
        return fid

    def soft_delete(self, file_id: str) -> None:
        self.conn.execute("UPDATE client_files SET is_active=0 WHERE id=?", (file_id,))
        self.conn.commit()
