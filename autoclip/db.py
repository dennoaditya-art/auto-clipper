from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL UNIQUE,
    duration REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    error TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    account_id TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    viral_score REAL NOT NULL,
    niche_fit REAL NOT NULL,
    final_score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    UNIQUE (source_id, start, end)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    approved_hash TEXT,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    remote_id TEXT,
    status TEXT NOT NULL,
    error TEXT,
    scheduled_at TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE (clip_id, platform, account_id)
);

CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_clips_source ON clips(source_id);
CREATE INDEX IF NOT EXISTS idx_publications_clip ON publications(clip_id);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    campaign_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    views INTEGER NOT NULL DEFAULT 0,
    payout REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'submitted',
    note TEXT,
    submitted_at TEXT NOT NULL,
    paid_at TEXT,
    UNIQUE (clip_id, campaign_id, platform)
);
"""


class DbError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(publications)").fetchall()
    }
    if "scheduled_at" not in cols:
        conn.execute("ALTER TABLE publications ADD COLUMN scheduled_at TEXT")


def create_source(
    conn: sqlite3.Connection, path: str, sha256: str, duration: float
) -> int | None:
    existing = conn.execute(
        "SELECT id FROM sources WHERE sha256 = ?", (sha256,)
    ).fetchone()
    if existing:
        return None
    try:
        cur = conn.execute(
            "INSERT INTO sources(path, sha256, duration, status, created_at) "
            "VALUES (?, ?, ?, 'new', ?)",
            (path, sha256, duration, now()),
        )
    except sqlite3.IntegrityError:
        return None
    conn.commit()
    return int(cur.lastrowid)


def get_source(conn: sqlite3.Connection, source_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise DbError(f"source {source_id} tidak ditemukan")
    return row


def find_source(conn: sqlite3.Connection, value: str) -> sqlite3.Row | None:
    if value.isdigit():
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (int(value),)).fetchone()
        if row is not None:
            return row
    return conn.execute("SELECT * FROM sources WHERE path = ?", (value,)).fetchone()


def list_sources(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return list(
            conn.execute(
                "SELECT * FROM sources WHERE status = ? ORDER BY id", (status,)
            )
        )
    return list(conn.execute("SELECT * FROM sources ORDER BY id"))


def set_source_status(
    conn: sqlite3.Connection, source_id: int, status: str, error: str | None = None
) -> None:
    processed = now() if status in {"processed", "failed"} else None
    conn.execute(
        "UPDATE sources SET status = ?, error = ?, processed_at = COALESCE(?, processed_at) "
        "WHERE id = ?",
        (status, error, processed, source_id),
    )
    conn.commit()


def create_job(conn: sqlite3.Connection, source_id: int, stage: str) -> int:
    cur = conn.execute(
        "INSERT INTO jobs(source_id, stage, status, started_at) VALUES (?, ?, 'running', ?)",
        (source_id, stage, now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_job(
    conn: sqlite3.Connection, job_id: int, status: str, error: str | None = None
) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
        (status, error, now(), job_id),
    )
    conn.commit()


def add_clip(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    account_id: str,
    start: float,
    end: float,
    file_path: str,
    file_hash: str,
    title: str,
    topic: str,
    scores_json: str,
    viral_score: float,
    niche_fit: float,
    final_score: float,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO clips(
            source_id, account_id, start, end, file_path, file_hash, title, topic,
            scores_json, viral_score, niche_fit, final_score, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        ON CONFLICT(source_id, start, end) DO UPDATE SET
            account_id = excluded.account_id,
            file_path = excluded.file_path,
            file_hash = excluded.file_hash,
            title = excluded.title,
            topic = excluded.topic,
            scores_json = excluded.scores_json,
            viral_score = excluded.viral_score,
            niche_fit = excluded.niche_fit,
            final_score = excluded.final_score,
            status = 'pending',
            created_at = excluded.created_at
        RETURNING id
        """,
        (
            source_id,
            account_id,
            start,
            end,
            file_path,
            file_hash,
            title,
            topic,
            scores_json,
            viral_score,
            niche_fit,
            final_score,
            now(),
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row[0])


def get_clip(conn: sqlite3.Connection, clip_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        raise DbError(f"clip {clip_id} tidak ditemukan")
    return row


def list_clips(
    conn: sqlite3.Connection, status: str | None = None
) -> list[sqlite3.Row]:
    sql = (
        "SELECT c.*, s.path AS source_path FROM clips c "
        "JOIN sources s ON s.id = c.source_id "
    )
    args: Iterable[Any] = ()
    if status:
        sql += "WHERE c.status = ? "
        args = (status,)
    sql += "ORDER BY c.final_score DESC, c.id"
    return list(conn.execute(sql, tuple(args)))


def clips_for_source(conn: sqlite3.Connection, source_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM clips WHERE source_id = ? ORDER BY start", (source_id,)
        )
    )


def set_clip_status(conn: sqlite3.Connection, clip_id: int, status: str) -> None:
    conn.execute("UPDATE clips SET status = ? WHERE id = ?", (status, clip_id))
    conn.commit()


def record_review(
    conn: sqlite3.Connection,
    clip_id: int,
    decision: str,
    reviewer: str,
    approved_hash: str | None,
) -> None:
    if decision not in {"approved", "rejected"}:
        raise DbError(f"keputusan tidak valid: {decision}")
    conn.execute(
        "INSERT INTO reviews(clip_id, decision, reviewer, approved_hash, decided_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (clip_id, decision, reviewer, approved_hash, now()),
    )
    set_clip_status(conn, clip_id, decision)
    conn.commit()


def latest_review(conn: sqlite3.Connection, clip_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reviews WHERE clip_id = ? ORDER BY id DESC LIMIT 1", (clip_id,)
    ).fetchone()


def count_sources(conn: sqlite3.Connection, status: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM sources WHERE status = ?", (status,)).fetchone()
    return int(row[0])


def get_publication(
    conn: sqlite3.Connection, clip_id: int, platform: str, account_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM publications WHERE clip_id = ? AND platform = ? AND account_id = ?",
        (clip_id, platform, account_id),
    ).fetchone()


def begin_publication(
    conn: sqlite3.Connection,
    clip_id: int,
    platform: str,
    account_id: str,
    scheduled_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO publications(clip_id, platform, account_id, status, scheduled_at, created_at)
        VALUES (?, ?, ?, 'uploading', ?, ?)
        ON CONFLICT(clip_id, platform, account_id) DO UPDATE SET
            status = 'uploading',
            error = NULL,
            scheduled_at = excluded.scheduled_at
        """,
        (clip_id, platform, account_id, scheduled_at, now()),
    )
    conn.commit()


def count_future_scheduled(conn: sqlite3.Connection) -> int:
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = conn.execute(
        "SELECT COUNT(*) FROM publications "
        "WHERE status = 'published' AND scheduled_at > ?",
        (cutoff,),
    ).fetchone()
    return int(row[0])


def future_scheduled_slots(conn: sqlite3.Connection) -> set[str]:
    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        "SELECT scheduled_at FROM publications "
        "WHERE status = 'published' AND scheduled_at IS NOT NULL AND scheduled_at > ?",
        (cutoff,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def finish_publication(
    conn: sqlite3.Connection,
    clip_id: int,
    platform: str,
    account_id: str,
    *,
    remote_id: str | None = None,
    error: str | None = None,
) -> None:
    status = "published" if remote_id and not error else "failed"
    published = now() if status == "published" else None
    conn.execute(
        """
        UPDATE publications
        SET status = ?, remote_id = ?, error = ?,
            published_at = COALESCE(?, published_at),
            scheduled_at = CASE WHEN ? = 'failed' THEN NULL ELSE scheduled_at END
        WHERE clip_id = ? AND platform = ? AND account_id = ?
        """,
        (status, remote_id, error, published, status, clip_id, platform, account_id),
    )
    conn.commit()

def record_claim(
    conn: sqlite3.Connection,
    clip_id: int,
    campaign_id: str,
    platform: str,
    url: str,
    views: int,
    payout: float,
    note: str | None = None,
) -> int:
    existing = conn.execute(
        "SELECT id FROM claims WHERE clip_id = ? AND campaign_id = ? AND platform = ?",
        (clip_id, campaign_id, platform),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE claims SET url = ?, views = ?, payout = ?, note = ? WHERE id = ?",
            (url, views, payout, note, int(existing[0])),
        )
        conn.commit()
        return int(existing[0])
    cur = conn.execute(
        "INSERT INTO claims(clip_id, campaign_id, platform, url, views, payout, "
        "status, note, submitted_at) VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?, ?)",
        (clip_id, campaign_id, platform, url, views, payout, note, now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def set_claim_status(conn: sqlite3.Connection, claim_id: int, status: str) -> None:
    paid = now() if status == "paid" else None
    conn.execute(
        "UPDATE claims SET status = ?, paid_at = COALESCE(?, paid_at) WHERE id = ?",
        (status, paid, claim_id),
    )
    conn.commit()


def list_claims(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM claims WHERE status = ? ORDER BY submitted_at DESC",
            (status,),
        ).fetchall()
    return conn.execute("SELECT * FROM claims ORDER BY submitted_at DESC").fetchall()


def claim_totals(conn: sqlite3.Connection) -> dict[str, float]:
    row = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(views),0) v, COALESCE(SUM(payout),0) p "
        "FROM claims"
    ).fetchone()
    paid = conn.execute(
        "SELECT COALESCE(SUM(payout),0) FROM claims WHERE status = 'paid'"
    ).fetchone()[0]
    return {
        "count": float(row["n"]),
        "views": float(row["v"]),
        "payout": float(row["p"]),
        "paid": float(paid),
    }
