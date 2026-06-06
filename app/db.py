"""SQLite persistence for calls, transcripts, and campaigns.

Tiny, dependency-free (stdlib sqlite3). A single shared connection guarded by a
lock; writes are sub-millisecond so handlers call these directly.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time

from . import config

DB_PATH = os.path.join(config.BASE_DIR, "data", "app.db")

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    sid         TEXT PRIMARY KEY,
    to_number   TEXT,
    from_number TEXT,
    direction   TEXT,            -- inbound | outbound
    status      TEXT,            -- queued|ringing|in-progress|completed|failed|...
    duration    INTEGER DEFAULT 0,
    name        TEXT,            -- student name captured during the call
    campaign_id INTEGER,
    created_at  REAL,
    updated_at  REAL
);
CREATE TABLE IF NOT EXISTS turns (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid  TEXT,
    turn      INTEGER,
    role      TEXT,              -- user | assistant
    text      TEXT,             -- English (advisor's working language)
    text_gu   TEXT,             -- Gujarati (what was actually spoken/heard)
    created_at REAL
);
CREATE TABLE IF NOT EXISTS campaigns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT,
    status     TEXT,             -- pending | running | completed
    created_at REAL
);
CREATE TABLE IF NOT EXISTS campaign_numbers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    number      TEXT,
    status      TEXT,            -- pending | calling | done | failed
    call_sid    TEXT,
    created_at  REAL
);
CREATE TABLE IF NOT EXISTS leads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT,
    phone         TEXT,
    qualification TEXT,
    interest      TEXT,
    status        TEXT,           -- new | contacted | interested | enrolled | lost
    source        TEXT,           -- call | manual | campaign
    notes         TEXT,
    call_sid      TEXT,
    created_at    REAL,
    updated_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_turns_call ON turns(call_sid);
CREATE INDEX IF NOT EXISTS idx_cn_campaign ON campaign_numbers(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
"""

LEAD_STATUSES = ["new", "contacted", "interested", "enrolled", "lost"]


def _now() -> float:
    return time.time()


def _c() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def init_db() -> None:
    with _lock:
        _c().executescript(SCHEMA)
        _c().commit()
        # Migrate older DBs that predate the calls.name column.
        cols = {r["name"] for r in _c().execute("PRAGMA table_info(calls)").fetchall()}
        if "name" not in cols:
            _c().execute("ALTER TABLE calls ADD COLUMN name TEXT")
            _c().commit()
        # Migrate older DBs that predate the turns.text_gu column.
        tcols = {r["name"] for r in _c().execute("PRAGMA table_info(turns)").fetchall()}
        if "text_gu" not in tcols:
            _c().execute("ALTER TABLE turns ADD COLUMN text_gu TEXT")
            _c().commit()
        # Any campaign left 'running' from a previous process can't resume.
        _c().execute("UPDATE campaigns SET status='completed' WHERE status='running'")
        _c().commit()


# --------------------------------------------------------------------------- #
# Calls
# --------------------------------------------------------------------------- #
def record_call(sid: str, to_number: str, from_number: str, direction: str,
                status: str, campaign_id: int | None = None) -> None:
    with _lock:
        _c().execute(
            """INSERT INTO calls (sid,to_number,from_number,direction,status,campaign_id,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(sid) DO UPDATE SET
                 to_number=excluded.to_number, from_number=excluded.from_number,
                 direction=excluded.direction, status=excluded.status,
                 campaign_id=COALESCE(excluded.campaign_id, calls.campaign_id),
                 updated_at=excluded.updated_at""",
            (sid, to_number, from_number, direction, status, campaign_id, _now(), _now()),
        )
        _c().commit()


def update_call_status(sid: str, status: str, duration: int | None = None) -> None:
    with _lock:
        if duration is not None:
            _c().execute("UPDATE calls SET status=?, duration=?, updated_at=? WHERE sid=?",
                         (status, duration, _now(), sid))
        else:
            _c().execute("UPDATE calls SET status=?, updated_at=? WHERE sid=?",
                         (status, _now(), sid))
        _c().commit()


def set_call_name(sid: str, name: str) -> None:
    """Store the student's name on the call row (best-effort; ignores blanks)."""
    if not name:
        return
    with _lock:
        _c().execute("UPDATE calls SET name=?, updated_at=? WHERE sid=?",
                     (name, _now(), sid))
        _c().commit()


def add_turn(call_sid: str, turn: int, role: str, text: str, text_gu: str = "") -> None:
    with _lock:
        _c().execute(
            "INSERT INTO turns (call_sid,turn,role,text,text_gu,created_at) VALUES (?,?,?,?,?,?)",
            (call_sid, turn, role, text, text_gu, _now()),
        )
        _c().commit()


def get_calls(limit: int = 200) -> list[dict]:
    rows = _c().execute(
        """SELECT c.*, COALESCE(t.n,0) AS turns, cp.name AS campaign_name
           FROM calls c
           LEFT JOIN (SELECT call_sid, COUNT(*) n FROM turns GROUP BY call_sid) t
                  ON t.call_sid = c.sid
           LEFT JOIN campaigns cp ON cp.id = c.campaign_id
           ORDER BY c.created_at DESC LIMIT ?""", (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_call(sid: str) -> dict | None:
    row = _c().execute("SELECT * FROM calls WHERE sid=?", (sid,)).fetchone()
    if not row:
        return None
    call = dict(row)
    call["transcript"] = [
        dict(r) for r in _c().execute(
            "SELECT turn,role,text,text_gu,created_at FROM turns WHERE call_sid=? ORDER BY id", (sid,)
        ).fetchall()
    ]
    return call


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
def create_campaign(name: str, numbers: list[str]) -> int:
    with _lock:
        cur = _c().execute(
            "INSERT INTO campaigns (name,status,created_at) VALUES (?,?,?)",
            (name, "pending", _now()),
        )
        cid = cur.lastrowid
        for n in numbers:
            _c().execute(
                "INSERT INTO campaign_numbers (campaign_id,number,status,created_at) VALUES (?,?,?,?)",
                (cid, n, "pending", _now()),
            )
        _c().commit()
        return cid


def set_campaign_status(cid: int, status: str) -> None:
    with _lock:
        _c().execute("UPDATE campaigns SET status=? WHERE id=?", (status, cid))
        _c().commit()


def set_number_status(num_id: int, status: str, call_sid: str | None = None) -> None:
    with _lock:
        if call_sid:
            _c().execute("UPDATE campaign_numbers SET status=?, call_sid=? WHERE id=?",
                         (status, call_sid, num_id))
        else:
            _c().execute("UPDATE campaign_numbers SET status=? WHERE id=?", (status, num_id))
        _c().commit()


def get_campaign_numbers(cid: int) -> list[dict]:
    return [dict(r) for r in _c().execute(
        "SELECT * FROM campaign_numbers WHERE campaign_id=? ORDER BY id", (cid,)).fetchall()]


def get_campaigns() -> list[dict]:
    rows = _c().execute(
        """SELECT c.*,
                  COUNT(n.id) AS total,
                  SUM(CASE WHEN n.status IN ('done','failed') THEN 1 ELSE 0 END) AS finished
           FROM campaigns c LEFT JOIN campaign_numbers n ON n.campaign_id=c.id
           GROUP BY c.id ORDER BY c.created_at DESC""").fetchall()
    return [dict(r) for r in rows]


def get_campaign(cid: int) -> dict | None:
    row = _c().execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    if not row:
        return None
    camp = dict(row)
    camp["numbers"] = get_campaign_numbers(cid)
    return camp


def stats() -> dict:
    total = _c().execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    completed = _c().execute("SELECT COUNT(*) FROM calls WHERE status='completed'").fetchone()[0]
    avg = _c().execute(
        "SELECT AVG(duration) FROM calls WHERE status='completed' AND duration>0").fetchone()[0]
    campaigns = _c().execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    leads = _c().execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    return {
        "total_calls": total,
        "completed_calls": completed,
        "avg_duration": round(avg or 0, 1),
        "campaigns": campaigns,
        "leads": leads,
    }


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #
def create_lead(name: str = "", phone: str = "", qualification: str = "",
                interest: str = "", status: str = "new", source: str = "manual",
                notes: str = "", call_sid: str | None = None) -> int:
    with _lock:
        cur = _c().execute(
            """INSERT INTO leads (name,phone,qualification,interest,status,source,notes,call_sid,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (name, phone, qualification, interest, status, source, notes, call_sid, _now(), _now()),
        )
        _c().commit()
        return cur.lastrowid


def upsert_lead_from_phone(phone: str, call_sid: str | None = None,
                           source: str = "call", name: str = "",
                           qualification: str = "") -> None:
    """Create a lead for this phone if none exists; else refresh its activity.

    `name`/`qualification` captured during a call are filled in only when the
    lead doesn't already have them, so a human edit is never clobbered.
    """
    if not phone:
        return
    with _lock:
        row = _c().execute(
            "SELECT id,name,qualification FROM leads WHERE phone=? LIMIT 1", (phone,)
        ).fetchone()
        if row:
            new_name = name or row["name"] or ""
            new_qual = qualification or row["qualification"] or ""
            _c().execute(
                "UPDATE leads SET name=?, qualification=?, call_sid=?, updated_at=? WHERE id=?",
                (new_name, new_qual, call_sid, _now(), row["id"]),
            )
        else:
            _c().execute(
                """INSERT INTO leads (name,phone,qualification,interest,status,source,notes,call_sid,created_at,updated_at)
                   VALUES (?,?,?,'','new',?, '',?,?,?)""",
                (name, phone, qualification, source, call_sid, _now(), _now()),
            )
        _c().commit()


def get_leads(status: str | None = None, limit: int = 500) -> list[dict]:
    if status:
        rows = _c().execute(
            "SELECT * FROM leads WHERE status=? ORDER BY updated_at DESC LIMIT ?",
            (status, limit)).fetchall()
    else:
        rows = _c().execute(
            "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def update_lead(lead_id: int, fields: dict) -> bool:
    allowed = {"name", "phone", "qualification", "interest", "status", "notes"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return False
    cols = ", ".join(f"{k}=?" for k in sets)
    with _lock:
        cur = _c().execute(f"UPDATE leads SET {cols}, updated_at=? WHERE id=?",
                           (*sets.values(), _now(), lead_id))
        _c().commit()
        return cur.rowcount > 0


def delete_lead(lead_id: int) -> bool:
    with _lock:
        cur = _c().execute("DELETE FROM leads WHERE id=?", (lead_id,))
        _c().commit()
        return cur.rowcount > 0


def lead_status_counts() -> dict:
    rows = _c().execute("SELECT status, COUNT(*) n FROM leads GROUP BY status").fetchall()
    counts = {s: 0 for s in LEAD_STATUSES}
    for r in rows:
        counts[r["status"]] = r["n"]
    return counts


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
def calls_by_day(days: int = 14) -> list[dict]:
    rows = _c().execute(
        """SELECT date(created_at,'unixepoch','localtime') AS day,
                  COUNT(*) AS total,
                  SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
           FROM calls
           WHERE created_at >= ?
           GROUP BY day ORDER BY day""",
        (_now() - days * 86400,),
    ).fetchall()
    return [dict(r) for r in rows]


def status_breakdown() -> dict:
    rows = _c().execute(
        "SELECT status, COUNT(*) n FROM calls GROUP BY status").fetchall()
    return {(r["status"] or "unknown"): r["n"] for r in rows}


def direction_breakdown() -> dict:
    rows = _c().execute(
        "SELECT direction, COUNT(*) n FROM calls GROUP BY direction").fetchall()
    return {(r["direction"] or "unknown"): r["n"] for r in rows}


def campaign_performance() -> list[dict]:
    rows = _c().execute(
        """SELECT c.name,
                  COUNT(n.id) AS total,
                  SUM(CASE WHEN n.status='done' THEN 1 ELSE 0 END) AS done,
                  SUM(CASE WHEN n.status='failed' THEN 1 ELSE 0 END) AS failed
           FROM campaigns c LEFT JOIN campaign_numbers n ON n.campaign_id=c.id
           GROUP BY c.id ORDER BY c.created_at DESC""").fetchall()
    return [dict(r) for r in rows]


def analytics() -> dict:
    total_talk = _c().execute(
        "SELECT COALESCE(SUM(duration),0) FROM calls WHERE status='completed'").fetchone()[0]
    return {
        "calls_by_day": calls_by_day(),
        "status_breakdown": status_breakdown(),
        "direction_breakdown": direction_breakdown(),
        "lead_status": lead_status_counts(),
        "campaign_performance": campaign_performance(),
        "total_talk_time": int(total_talk or 0),
    }


def overview() -> dict:
    today = _c().execute(
        """SELECT COUNT(*) FROM calls
           WHERE date(created_at,'unixepoch','localtime') = date('now','localtime')"""
    ).fetchone()[0]
    leads = lead_status_counts()
    s = stats()
    return {
        **s,
        "calls_today": today,
        "lead_status": leads,
        "calls_by_day": calls_by_day(7),
        "status_breakdown": status_breakdown(),
        "recent_calls": get_calls(6),
    }
