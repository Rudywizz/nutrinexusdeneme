import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ClinicalProfile:
    client_id: str
    diseases: str = ""
    allergies: str = ""
    intolerances: str = ""
    medications: str = ""
    supplements: str = ""
    lifestyle: str = ""
    activity_level: str = ""
    sleep: str = ""
    stress: str = ""
    smoking: str = ""
    alcohol: str = ""
    water: str = ""
    updated_at: str = ""


class ClinicalService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_profile(self, client_id: str) -> ClinicalProfile | None:
        cur = self.conn.execute("SELECT * FROM clinical_profiles WHERE client_id = ?", (client_id,))
        r = cur.fetchone()
        if not r:
            return None
        return ClinicalProfile(
            client_id=r["client_id"],
            diseases=r["diseases"],
            allergies=r["allergies"],
            intolerances=r["intolerances"],
            medications=r["medications"],
            supplements=r["supplements"],
            lifestyle=r["lifestyle"],
            activity_level=r["activity_level"],
            sleep=r["sleep"],
            stress=r["stress"],
            smoking=r["smoking"],
            alcohol=r["alcohol"],
            water=r["water"],
            updated_at=r["updated_at"],
        )

    def upsert_profile(self, profile: ClinicalProfile) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO clinical_profiles(
              client_id, diseases, allergies, intolerances, medications, supplements,
              lifestyle, activity_level, sleep, stress, smoking, alcohol, water, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(client_id) DO UPDATE SET
              diseases=excluded.diseases,
              allergies=excluded.allergies,
              intolerances=excluded.intolerances,
              medications=excluded.medications,
              supplements=excluded.supplements,
              lifestyle=excluded.lifestyle,
              activity_level=excluded.activity_level,
              sleep=excluded.sleep,
              stress=excluded.stress,
              smoking=excluded.smoking,
              alcohol=excluded.alcohol,
              water=excluded.water,
              updated_at=excluded.updated_at
            """,
            (
                profile.client_id,
                profile.diseases or "",
                profile.allergies or "",
                profile.intolerances or "",
                profile.medications or "",
                profile.supplements or "",
                profile.lifestyle or "",
                profile.activity_level or "",
                profile.sleep or "",
                profile.stress or "",
                profile.smoking or "",
                profile.alcohol or "",
                profile.water or "",
                now,
            ),
        )
        self.conn.commit()