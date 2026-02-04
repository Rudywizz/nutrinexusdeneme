import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

APP_VERSION = "0.0.0-sprint0"

@dataclass
class DraftKey:
    entity_type: str
    entity_id: str | None = None
    client_id: str | None = None

def upsert_draft(conn: sqlite3.Connection, key: DraftKey, payload: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload, ensure_ascii=False)

    # Aynı entity için tek taslak tutalım (basit/kararlı)
    conn.execute(
        """DELETE FROM autosave_drafts
            WHERE entity_type = ? AND IFNULL(entity_id,'') = IFNULL(?, '')
              AND IFNULL(client_id,'') = IFNULL(?, '')""",
        (key.entity_type, key.entity_id, key.client_id),
    )

    conn.execute(
        """INSERT INTO autosave_drafts(entity_type, entity_id, client_id, payload_json, updated_at, app_version)
            VALUES (?, ?, ?, ?, ?, ?)""",
        (key.entity_type, key.entity_id, key.client_id, payload_json, now, APP_VERSION),
    )
    conn.commit()

def fetch_latest_draft(conn: sqlite3.Connection, key: DraftKey) -> dict | None:
    cur = conn.execute(
        """SELECT payload_json FROM autosave_drafts
            WHERE entity_type = ? AND IFNULL(entity_id,'') = IFNULL(?, '')
              AND IFNULL(client_id,'') = IFNULL(?, '')
            ORDER BY updated_at DESC LIMIT 1""",
        (key.entity_type, key.entity_id, key.client_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return json.loads(row["payload_json"])

def clear_draft(conn: sqlite3.Connection, key: DraftKey) -> None:
    conn.execute(
        """DELETE FROM autosave_drafts
            WHERE entity_type = ? AND IFNULL(entity_id,'') = IFNULL(?, '')
              AND IFNULL(client_id,'') = IFNULL(?, '')""",
        (key.entity_type, key.entity_id, key.client_id),
    )
    conn.commit()
