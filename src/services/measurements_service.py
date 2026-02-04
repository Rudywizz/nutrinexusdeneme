import sqlite3
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class Measurement:
    id: str
    client_id: str
    measured_at: str  # YYYY-MM-DD
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    neck_cm: float | None = None
    body_fat_percent: float | None = None
    muscle_kg: float | None = None
    water_percent: float | None = None
    visceral_fat: float | None = None
    notes: str = ""

    def bmi(self) -> float | None:
        if not self.height_cm or not self.weight_kg:
            return None
        h_m = self.height_cm / 100.0
        if h_m <= 0:
            return None
        return self.weight_kg / (h_m * h_m)


class MeasurementsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def list_for_client(self, client_id: str) -> list[Measurement]:
        cur = self.conn.execute(
            """SELECT * FROM measurements WHERE client_id = ?
               ORDER BY measured_at DESC, created_at DESC""",
            (client_id,),
        )
        out: list[Measurement] = []
        for r in cur.fetchall():
            out.append(self._from_row(r))
        return out

    def latest_for_client(self, client_id: str) -> Measurement | None:
        cur = self.conn.execute(
            """SELECT * FROM measurements WHERE client_id = ?
               ORDER BY measured_at DESC, created_at DESC LIMIT 1""",
            (client_id,),
        )
        r = cur.fetchone()
        return self._from_row(r) if r else None

    def get_latest_measurement(self, client_id: str) -> Measurement | None:
        """Backward-compatible alias for latest_for_client."""
        return self.latest_for_client(client_id)

    def trend_points(self, client_id: str, days: int | None = None) -> list[tuple[str, float]]:
        """Return (measured_at, weight_kg) points for trend charts.

        - Filters by last `days` if provided (using measured_at as YYYY-MM-DD).
        - Excludes null/zero weights.
        - If multiple measurements exist on the same day, keeps the last created one.
        - Returns points sorted by date ascending.
        """
        params = [client_id]
        where = "client_id = ? AND weight_kg IS NOT NULL AND weight_kg > 0"
        if days is not None:
            where += " AND measured_at >= date('now', ?)"
            params.append(f"-{int(days)} day")

        cur = self.conn.execute(
            f"""SELECT measured_at, weight_kg, created_at
                 FROM measurements
                 WHERE {where}
                 ORDER BY measured_at ASC, created_at ASC""",
            tuple(params),
        )

        by_day: dict[str, float] = {}
        for measured_at, weight_kg, _created_at in cur.fetchall():
            # Because we iterate ASC, assigning overwrites -> keeps the last record of the day
            try:
                w = float(weight_kg)
            except Exception:
                continue
            if w <= 0:
                continue
            by_day[str(measured_at)] = w

        # Sort by date string (YYYY-MM-DD sorts lexicographically)
        return [(d, by_day[d]) for d in sorted(by_day.keys())]


    def create(
        self,
        client_id: str,
        measured_at: str,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        waist_cm: float | None = None,
        hip_cm: float | None = None,
        neck_cm: float | None = None,
        body_fat_percent: float | None = None,
        muscle_kg: float | None = None,
        water_percent: float | None = None,
        visceral_fat: float | None = None,
        notes: str = "",
    ) -> Measurement:
        now = datetime.now().isoformat(timespec="seconds")
        mid = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO measurements(
                id, client_id, measured_at,
                height_cm, weight_kg, waist_cm, hip_cm, neck_cm,
                body_fat_percent, muscle_kg, water_percent, visceral_fat,
                notes, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                mid,
                client_id,
                measured_at,
                height_cm,
                weight_kg,
                waist_cm,
                hip_cm,
                neck_cm,
                body_fat_percent,
                muscle_kg,
                water_percent,
                visceral_fat,
                notes or "",
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.get(mid)

    def get(self, measurement_id: str) -> Measurement | None:
        cur = self.conn.execute("SELECT * FROM measurements WHERE id = ?", (measurement_id,))
        r = cur.fetchone()
        return self._from_row(r) if r else None

    def update(
        self,
        measurement_id: str,
        measured_at: str,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        waist_cm: float | None = None,
        hip_cm: float | None = None,
        neck_cm: float | None = None,
        body_fat_percent: float | None = None,
        muscle_kg: float | None = None,
        water_percent: float | None = None,
        visceral_fat: float | None = None,
        notes: str = "",
    ) -> Measurement | None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """UPDATE measurements SET
                measured_at = ?,
                height_cm = ?, weight_kg = ?,
                waist_cm = ?, hip_cm = ?, neck_cm = ?,
                body_fat_percent = ?, muscle_kg = ?, water_percent = ?, visceral_fat = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?""",
            (
                measured_at,
                height_cm,
                weight_kg,
                waist_cm,
                hip_cm,
                neck_cm,
                body_fat_percent,
                muscle_kg,
                water_percent,
                visceral_fat,
                notes or "",
                now,
                measurement_id,
            ),
        )
        self.conn.commit()
        return self.get(measurement_id)

    def delete(self, measurement_id: str) -> None:
        self.conn.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))
        self.conn.commit()

    def _from_row(self, r) -> Measurement:
        return Measurement(
            id=r["id"],
            client_id=r["client_id"],
            measured_at=r["measured_at"],
            height_cm=r["height_cm"],
            weight_kg=r["weight_kg"],
            waist_cm=r["waist_cm"],
            hip_cm=r["hip_cm"],
            neck_cm=r["neck_cm"],
            body_fat_percent=r["body_fat_percent"],
            muscle_kg=r["muscle_kg"],
            water_percent=r["water_percent"],
            visceral_fat=r["visceral_fat"],
            notes=r["notes"] or "",
        )
