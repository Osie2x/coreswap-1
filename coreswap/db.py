import sqlite3
import json
import os
from datetime import datetime
from .config import DB_PATH
from .models import FactoryProfile, LCAResult, ReportRecord


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                company_name TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                lca_json TEXT NOT NULL,
                narrative TEXT NOT NULL,
                pdf_path TEXT NOT NULL
            )
        """)
        con.commit()


def save_report(profile: FactoryProfile, lca: LCAResult, narrative: str, pdf_path: str) -> int:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO reports (created_at, company_name, profile_json, lca_json, narrative, pdf_path) VALUES (?,?,?,?,?,?)",
            (now, profile.company_name, profile.model_dump_json(), lca.model_dump_json(), narrative, pdf_path),
        )
        con.commit()
        return cur.lastrowid


def list_reports() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, created_at, company_name FROM reports ORDER BY id DESC"
        ).fetchall()
    return [{"id": r[0], "created_at": r[1], "company_name": r[2]} for r in rows]


def load_report(report_id: int) -> ReportRecord | None:
    with _conn() as con:
        row = con.execute(
            "SELECT id, created_at, profile_json, lca_json, narrative, pdf_path FROM reports WHERE id=?",
            (report_id,),
        ).fetchone()
    if row is None:
        return None
    profile = FactoryProfile.model_validate_json(row[2])
    lca = LCAResult.model_validate_json(row[3])
    return ReportRecord(
        id=row[0],
        created_at=datetime.fromisoformat(row[1]),
        profile=profile,
        lca=lca,
        narrative_summary=row[4],
        pdf_path=row[5],
    )
