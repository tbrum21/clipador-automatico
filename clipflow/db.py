"""Registro simples de cortes (SQLite)."""
import sqlite3
from datetime import datetime

from . import config as C


def _conn():
    c = sqlite3.connect(C.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(
        """CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created TEXT, channel TEXT, path TEXT, title TEXT,
            score INTEGER, status TEXT
        )"""
    )
    c.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, channel TEXT NOT NULL,
        peak_time TEXT NOT NULL, info TEXT NOT NULL, status TEXT NOT NULL,
        raw_path TEXT, clip_id INTEGER, error TEXT, updated TEXT NOT NULL
    )""")
    c.execute('''CREATE TABLE IF NOT EXISTS recording_analyses (
        id INTEGER PRIMARY KEY, created TEXT NOT NULL, filename TEXT NOT NULL, status TEXT NOT NULL,
        progress TEXT NOT NULL, error TEXT, provider TEXT NOT NULL, settings TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS recording_candidates (
        id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
        title TEXT NOT NULL, score INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'sugerido',
        clip_id INTEGER, decision TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS hourly_assets (
        filename TEXT PRIMARY KEY, analysis_id INTEGER NOT NULL UNIQUE, size INTEGER NOT NULL,
        modified_ns INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'disponivel', error TEXT
    )''')
    columns = {row['name'] for row in c.execute('PRAGMA table_info(clips)')}
    for name in ('analysis_method', 'ai_provider', 'ai_model', 'ai_decision'):
        if name not in columns:
            try:
                c.execute(f'ALTER TABLE clips ADD COLUMN {name} TEXT')
            except sqlite3.OperationalError as exc:
                if 'duplicate column name' not in str(exc).lower():
                    raise
    return c


def add_clip(channel, path, title, score, status="aguardando_aprovacao", *, method=None, provider=None, model=None, decision=None) -> int:
    import json
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO clips (created, channel, path, title, score, status, analysis_method, ai_provider, ai_model, ai_decision) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), channel, str(path), title, score, status, method, provider, model,
             json.dumps(decision, ensure_ascii=False) if decision else None),
        )
        return cur.lastrowid


def get_clip(clip_id: int):
    with _conn() as c:
        return c.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()


def set_status(clip_id: int, status: str):
    with _conn() as c:
        c.execute("UPDATE clips SET status=? WHERE id=?", (status, clip_id))
    from .automatic import maybe_delete_for_clip
    maybe_delete_for_clip(clip_id)


def counts():
    with _conn() as c:
        return {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM clips GROUP BY status")}


def add_job(channel, peak_time, info):
    import json
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        return c.execute("INSERT INTO jobs (created, channel, peak_time, info, status, updated) VALUES (?, ?, ?, ?, ?, ?)",
                         (now, channel, peak_time.isoformat(), json.dumps(info), 'detectado', now)).lastrowid


def update_job(job_id, status, *, raw_path=None, clip_id=None, error=None):
    with _conn() as c:
        c.execute("""UPDATE jobs SET status=?, updated=?, raw_path=COALESCE(?, raw_path),
                     clip_id=COALESCE(?, clip_id), error=? WHERE id=?""",
                  (status, datetime.now().isoformat(timespec='seconds'), str(raw_path) if raw_path else None,
                   clip_id, error, job_id))


def list_jobs(limit=100):
    with _conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT ?', (limit,))]
