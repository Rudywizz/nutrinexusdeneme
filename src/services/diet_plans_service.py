import sqlite3
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class DietPlan:
    id: str
    client_id: str
    title: str
    start_date: str
    end_date: str
    plan_text: str
    notes: str
    is_active_plan: int
    created_at: str
    updated_at: str

class DietPlansService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_for_client(self, client_id: str) -> list[DietPlan]:
        cur = self.conn.execute(
            """SELECT id, client_id, title, start_date, end_date, plan_text, notes,
                      is_active_plan, created_at, updated_at
               FROM diet_plans
               WHERE client_id=? AND is_active=1
               ORDER BY start_date DESC, created_at DESC""",
            (client_id,),
        )
        rows = cur.fetchall()
        return [DietPlan(*row) for row in rows]

    def get(self, plan_id: str) -> DietPlan | None:
        cur = self.conn.execute(
            """SELECT id, client_id, title, start_date, end_date, plan_text, notes,
                      is_active_plan, created_at, updated_at
               FROM diet_plans
               WHERE id=? AND is_active=1""",
            (plan_id,),
        )
        row = cur.fetchone()
        return DietPlan(*row) if row else None

    def create(self, client_id: str, title: str, start_date: str, end_date: str = "",
               plan_text: str = "", notes: str = "", make_active: bool = True) -> str:
        pid = str(uuid.uuid4())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if make_active:
            self.conn.execute("UPDATE diet_plans SET is_active_plan=0 WHERE client_id=? AND is_active=1", (client_id,))
        self.conn.execute(
            """INSERT INTO diet_plans
               (id, client_id, title, start_date, end_date, plan_text, notes,
                is_active_plan, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (pid, client_id, title.strip(), start_date.strip(), (end_date or "").strip(),
             (plan_text or ""), (notes or ""), 1 if make_active else 0, now, now),
        )
        self.conn.commit()
        return pid

    def update(self, plan_id: str, title: str, start_date: str, end_date: str,
               plan_text: str, notes: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """UPDATE diet_plans
               SET title=?, start_date=?, end_date=?, plan_text=?, notes=?, updated_at=?
               WHERE id=?""",
            (title.strip(), start_date.strip(), (end_date or "").strip(),
             (plan_text or ""), (notes or ""), now, plan_id),
        )
        self.conn.commit()

    def set_active(self, plan_id: str) -> None:
        plan = self.get(plan_id)
        if not plan:
            return
        self.conn.execute("UPDATE diet_plans SET is_active_plan=0 WHERE client_id=? AND is_active=1", (plan.client_id,))
        self.conn.execute("UPDATE diet_plans SET is_active_plan=1 WHERE id=?", (plan_id,))
        self.conn.commit()

    def soft_delete(self, plan_id: str) -> None:
        self.conn.execute("UPDATE diet_plans SET is_active=0 WHERE id=?", (plan_id,))
        self.conn.commit()
