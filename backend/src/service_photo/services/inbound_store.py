"""
SQLite durability layer for the /inbound pipeline (Phase 7A).

What this replaces:
  1. The in-memory `_jobs` dict in api/inbound_routes.py — extraction job
     progress now survives server restarts and is visible across multiple
     uvicorn workers (lifting the `--workers 1` constraint in the Dockerfile).
  2. The browser-localStorage review/approval state — review edits and
     approvals now persist server-side, with an append-only audit trail of
     who edited/approved/exported what and when.

What this deliberately does NOT replace:
  The Gemini extraction artifacts (inbound/*.json) stay on the filesystem.
  They are the immutable "draft" layer (AI output); this database owns only
  the mutable "review" layer (human state). That mirrors the project's
  draft-vs-review ADR (docs/decisions/0001).

Storage:
  A single SQLite file at <APP_DATA_PATH>/catalog.db — on Railway that is
  /data/catalog.db (the mounted volume), locally it's the repo root.
  Stdlib sqlite3 only — no new dependency, and nothing here is orphaned when
  the dormant /jobs pipeline (SQLAlchemy/Postgres) is deleted.

Concurrency model:
  - WAL journal mode: readers never block the writer, which matters once
    uvicorn runs multiple workers all polling job status.
  - busy_timeout: a writer that finds the database locked waits instead of
    failing immediately.
  - Every public function opens its own short-lived connection. SQLite
    connections are cheap, and per-call connections sidestep all
    cross-thread connection-sharing rules.
  - The single-active-extraction invariant is enforced with BEGIN IMMEDIATE
    (take the write lock up front), so two simultaneous POST /extract
    requests — even from different worker processes — cannot both pass the
    "is anything running?" check.

Tables (see _SCHEMA below):
  extraction_jobs        — one row per extraction run (replaces _jobs values)
  extraction_job_images  — per-image outcomes within a run
  review_items           — current review state, one row per card (JSON blobs)
  review_events          — append-only audit trail (never UPDATEd or DELETEd
                           except by the full Clear Data reset)
  exports                — provenance of every CSV written
"""

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from service_photo.core.config import APP_DATA_PATH

# --- Location ------------------------------------------------------------------
# Module-level so tests can monkeypatch it to a temp file, the same pattern the
# inbound tests already use for INBOUND_DIR / EXPORTS_DIR.
DB_PATH: Path = APP_DATA_PATH / "catalog.db"

# An extraction job that hasn't written any progress for this long is treated
# as orphaned (the server restarted mid-run and the worker thread died with
# it). The stale check runs lazily on read and on new-job creation, NOT at
# startup — an unconditional startup sweep would let one respawned uvicorn
# worker kill a job legitimately running in a sibling worker's thread.
# 300s comfortably exceeds the worst legitimate silence between progress
# writes (a single Gemini call capped at GEMINI_TIMEOUT_SECONDS=150).
STALE_ACTIVE_JOB_SECONDS = 300

# Statuses that mean "an extraction is in flight".
_ACTIVE_STATUSES = ("queued", "running")

# Schema version for PRAGMA user_version. Bump + append migration steps in
# _migrate() if the schema ever changes after release.
_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS extraction_jobs (
    job_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed')),
    total           INTEGER NOT NULL,
    completed       INTEGER NOT NULL DEFAULT 0,
    succeeded       INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    current_image   TEXT,
    batch_name      TEXT,
    started_at_utc  TEXT NOT NULL,
    finished_at_utc TEXT,
    model           TEXT,
    error           TEXT,
    -- Heartbeat: bumped on every mutation. Drives the orphaned-job check.
    updated_at_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_job_images (
    job_id        TEXT NOT NULL REFERENCES extraction_jobs(job_id) ON DELETE CASCADE,
    image_name    TEXT NOT NULL,
    success       INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    api_error     TEXT,
    schema_valid  INTEGER NOT NULL,
    schema_error  TEXT,
    -- Completion order, so results render in the order they finished.
    finished_rank INTEGER NOT NULL,
    PRIMARY KEY (job_id, image_name)
);

CREATE TABLE IF NOT EXISTS review_items (
    extraction_id    TEXT PRIMARY KEY,
    edited_response  TEXT NOT NULL,   -- JSON blob of the (possibly edited) ListingResponse
    edited_pricing   TEXT,            -- JSON blob, or NULL when Gemini returned no pricing
    approved         INTEGER NOT NULL DEFAULT 0,
    approved_at_utc  TEXT,
    approved_by      TEXT,
    updated_at_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_id  TEXT NOT NULL,
    event_type     TEXT NOT NULL CHECK (event_type IN ('edited','approved','unapproved','exported')),
    actor          TEXT,
    at_utc         TEXT NOT NULL,
    detail         TEXT              -- JSON: edit snapshot, or {"csv_filename": ...} for exports
);

CREATE TABLE IF NOT EXISTS exports (
    export_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    csv_filename    TEXT NOT NULL,
    row_count       INTEGER NOT NULL,
    exported_at_utc TEXT NOT NULL,
    actor           TEXT,
    extraction_ids  TEXT NOT NULL    -- JSON array of the ids included in the CSV
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON extraction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_events_extraction ON review_events(extraction_id);
"""

# Paths whose schema we've already created this process — avoids re-running
# DDL on every call. Guarded by a lock because FastAPI handlers run in a
# thread pool.
_initialized_paths: set[str] = set()
_init_lock = threading.Lock()


class ActiveJobError(Exception):
    """Raised by create_job when another extraction is already in flight.

    Carries the active job's snapshot so the route can build a helpful 409.
    """

    def __init__(self, active_job: dict):
        self.active_job = active_job
        super().__init__(
            f"extraction {active_job['job_id']} is already {active_job['status']}"
        )


def _now_iso() -> str:
    """Seconds-precision UTC ISO8601, matching every other timestamp in the app."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    """Open a configured connection, creating the schema on first use of a path."""
    path = DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL lets the multi-worker deployment read job status while the
    # extraction worker writes progress. busy_timeout makes writers wait
    # (up to 10s) instead of erroring when the write lock is briefly held.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")

    key = str(path)
    if key not in _initialized_paths:
        with _init_lock:
            if key not in _initialized_paths:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                conn.commit()
                _initialized_paths.add(key)
    return conn


def init_db() -> None:
    """Eagerly create the schema. Called at app startup so the first real
    request doesn't pay the DDL cost and config errors surface immediately."""
    with closing(_connect()):
        pass


# --- Internal helpers -----------------------------------------------------------

def _job_row_to_dict(row: sqlite3.Row, results: list[dict]) -> dict:
    """Shape one extraction_jobs row like the ExtractionJob pydantic model."""
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "total": row["total"],
        "completed": row["completed"],
        "succeeded": row["succeeded"],
        "failed": row["failed"],
        "current_image": row["current_image"],
        "started_at_utc": row["started_at_utc"],
        "finished_at_utc": row["finished_at_utc"],
        "model": row["model"],
        "error": row["error"],
        "results": results,
    }


def _load_job_results(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT image_name, success, duration_ms, api_error, schema_valid, schema_error
           FROM extraction_job_images WHERE job_id = ? ORDER BY finished_rank""",
        (job_id,),
    ).fetchall()
    return [
        {
            "image_name": r["image_name"],
            "success": bool(r["success"]),
            "duration_ms": r["duration_ms"],
            "api_error": r["api_error"],
            "schema_valid": bool(r["schema_valid"]),
            "schema_error": r["schema_error"],
        }
        for r in rows
    ]


def _fail_if_stale(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
    """If an active job's heartbeat is older than the stale threshold, flip it
    to failed (the worker thread died with a previous server process) and
    return the refreshed row. No-op for healthy or terminal jobs."""
    if row["status"] not in _ACTIVE_STATUSES:
        return row
    try:
        updated = datetime.strptime(row["updated_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError):
        return row
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    if age <= STALE_ACTIVE_JOB_SECONDS:
        return row
    now = _now_iso()
    conn.execute(
        """UPDATE extraction_jobs
           SET status = 'failed',
               error = 'extraction lost — the server restarted while this run was in progress',
               finished_at_utc = ?, current_image = NULL, updated_at_utc = ?
           WHERE job_id = ? AND status IN ('queued','running')""",
        (now, now, row["job_id"]),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM extraction_jobs WHERE job_id = ?", (row["job_id"],)
    ).fetchone()


def _add_event(
    conn: sqlite3.Connection,
    extraction_id: str,
    event_type: str,
    actor: str | None,
    detail: dict | None = None,
) -> None:
    """Append one audit row inside the caller's open transaction."""
    conn.execute(
        "INSERT INTO review_events (extraction_id, event_type, actor, at_utc, detail) VALUES (?,?,?,?,?)",
        (
            extraction_id,
            event_type,
            actor,
            _now_iso(),
            json.dumps(detail, ensure_ascii=False) if detail is not None else None,
        ),
    )


# --- Extraction jobs ------------------------------------------------------------

def create_job(
    job_id: str,
    total: int,
    started_at_utc: str,
    batch_name: str | None,
) -> None:
    """Register a new extraction job, enforcing the single-active-run lock.

    BEGIN IMMEDIATE takes SQLite's write lock before the SELECT, so two
    concurrent calls (same worker or different workers) serialize here — the
    loser of the race sees the winner's row and raises ActiveJobError.
    """
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            "SELECT * FROM extraction_jobs WHERE status IN ('queued','running') LIMIT 1"
        ).fetchone()
        if active is not None:
            # A stale orphan shouldn't block new work forever — check before 409ing.
            active = _fail_if_stale(conn, active)
        if active is not None and active["status"] in _ACTIVE_STATUSES:
            conn.rollback()
            raise ActiveJobError(_job_row_to_dict(active, []))
        now = _now_iso()
        conn.execute(
            """INSERT INTO extraction_jobs
               (job_id, status, total, batch_name, started_at_utc, updated_at_utc)
               VALUES (?, 'queued', ?, ?, ?, ?)""",
            (job_id, total, batch_name, started_at_utc, now),
        )
        conn.commit()


def get_job(job_id: str) -> dict | None:
    """Fetch one job (with per-image results), applying the stale-orphan check."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM extraction_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        row = _fail_if_stale(conn, row)
        return _job_row_to_dict(row, _load_job_results(conn, job_id))


def update_job(job_id: str, **fields) -> None:
    """Set arbitrary columns on a job row and bump the heartbeat.

    Used by the extraction worker for status flips (queued→running,
    →completed/→failed) and current_image updates.
    """
    if not fields:
        return
    columns = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values())
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE extraction_jobs SET {columns}, updated_at_utc = ? WHERE job_id = ?",  # noqa: S608 — column names come from our own code, never user input
            [*values, _now_iso(), job_id],
        )
        conn.commit()


def record_image_result(
    job_id: str,
    image_name: str,
    success: bool,
    duration_ms: int,
    api_error: str | None,
    schema_valid: bool,
    schema_error: str | None,
) -> None:
    """Record one finished image: insert its row and update the job counters
    in a single transaction, mirroring the old _on_image_done mutation."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rank_row = conn.execute(
            "SELECT COUNT(*) AS n FROM extraction_job_images WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        conn.execute(
            """INSERT OR REPLACE INTO extraction_job_images
               (job_id, image_name, success, duration_ms, api_error, schema_valid, schema_error, finished_rank)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                job_id,
                image_name,
                int(success),
                duration_ms,
                api_error,
                int(schema_valid),
                schema_error,
                rank_row["n"],
            ),
        )
        # Counter bumps; clear current_image when the run is fully done
        # (mid-run it always points at *some* in-flight image — see the
        # parallel-extraction note in inbound_routes).
        conn.execute(
            """UPDATE extraction_jobs SET
                 completed = completed + 1,
                 succeeded = succeeded + ?,
                 failed = failed + ?,
                 current_image = CASE WHEN completed + 1 >= total THEN NULL ELSE current_image END,
                 updated_at_utc = ?
               WHERE job_id = ?""",
            (int(success), int(not success), _now_iso(), job_id),
        )
        conn.commit()


# --- Review state -----------------------------------------------------------------

def get_all_reviews() -> dict[str, dict]:
    """Return every review row keyed by extraction_id, JSON blobs decoded."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM review_items").fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out[r["extraction_id"]] = {
            "edited_response": json.loads(r["edited_response"]),
            "edited_pricing": json.loads(r["edited_pricing"]) if r["edited_pricing"] else None,
            "approved": bool(r["approved"]),
            "approved_at_utc": r["approved_at_utc"],
            "approved_by": r["approved_by"],
            "updated_at_utc": r["updated_at_utc"],
        }
    return out


def save_review(
    extraction_id: str,
    edited_response: dict,
    edited_pricing: dict | None,
    actor: str | None,
) -> dict:
    """Upsert a card's edited content (approval state untouched) + audit event.

    Returns the stored row in get_all_reviews() shape.
    """
    now = _now_iso()
    response_json = json.dumps(edited_response, ensure_ascii=False)
    pricing_json = json.dumps(edited_pricing, ensure_ascii=False) if edited_pricing is not None else None
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO review_items
                 (extraction_id, edited_response, edited_pricing, updated_at_utc)
               VALUES (?,?,?,?)
               ON CONFLICT(extraction_id) DO UPDATE SET
                 edited_response = excluded.edited_response,
                 edited_pricing = excluded.edited_pricing,
                 updated_at_utc = excluded.updated_at_utc""",
            (extraction_id, response_json, pricing_json, now),
        )
        # The audit detail is the full saved snapshot — small (a few KB) and
        # makes "what did the content look like after this edit?" answerable.
        _add_event(conn, extraction_id, "edited", actor,
                   {"response": edited_response, "pricing": edited_pricing})
        row = conn.execute(
            "SELECT * FROM review_items WHERE extraction_id = ?", (extraction_id,)
        ).fetchone()
        conn.commit()
    return {
        "edited_response": json.loads(row["edited_response"]),
        "edited_pricing": json.loads(row["edited_pricing"]) if row["edited_pricing"] else None,
        "approved": bool(row["approved"]),
        "approved_at_utc": row["approved_at_utc"],
        "approved_by": row["approved_by"],
        "updated_at_utc": row["updated_at_utc"],
    }


def set_approval(
    extraction_id: str,
    approved: bool,
    actor: str | None,
    edited_response: dict | None = None,
    edited_pricing: dict | None = None,
) -> dict:
    """Approve or un-approve a card, creating the review row if needed.

    The approve call carries the card's current content so approving a
    never-edited card still snapshots exactly what the human saw and signed
    off on. Un-approve leaves content untouched.
    """
    now = _now_iso()
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM review_items WHERE extraction_id = ?", (extraction_id,)
        ).fetchone()
        if existing is None:
            if edited_response is None:
                conn.rollback()
                raise ValueError(
                    f"no review row for {extraction_id} and no content provided to create one"
                )
            conn.execute(
                """INSERT INTO review_items
                     (extraction_id, edited_response, edited_pricing,
                      approved, approved_at_utc, approved_by, updated_at_utc)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    extraction_id,
                    json.dumps(edited_response, ensure_ascii=False),
                    json.dumps(edited_pricing, ensure_ascii=False) if edited_pricing is not None else None,
                    int(approved),
                    now if approved else None,
                    actor if approved else None,
                    now,
                ),
            )
        else:
            # On approve, refresh the content snapshot too when provided —
            # the human approves what's on screen, not what was last saved.
            sets = ["approved = ?", "approved_at_utc = ?", "approved_by = ?", "updated_at_utc = ?"]
            values: list[object] = [
                int(approved),
                now if approved else None,
                actor if approved else None,
                now,
            ]
            if approved and edited_response is not None:
                sets.insert(0, "edited_response = ?")
                values.insert(0, json.dumps(edited_response, ensure_ascii=False))
                sets.insert(1, "edited_pricing = ?")
                values.insert(
                    1,
                    json.dumps(edited_pricing, ensure_ascii=False) if edited_pricing is not None else None,
                )
            conn.execute(
                f"UPDATE review_items SET {', '.join(sets)} WHERE extraction_id = ?",  # noqa: S608
                [*values, extraction_id],
            )
        _add_event(conn, extraction_id, "approved" if approved else "unapproved", actor)
        row = conn.execute(
            "SELECT * FROM review_items WHERE extraction_id = ?", (extraction_id,)
        ).fetchone()
        conn.commit()
    return {
        "edited_response": json.loads(row["edited_response"]),
        "edited_pricing": json.loads(row["edited_pricing"]) if row["edited_pricing"] else None,
        "approved": bool(row["approved"]),
        "approved_at_utc": row["approved_at_utc"],
        "approved_by": row["approved_by"],
        "updated_at_utc": row["updated_at_utc"],
    }


def get_approved_reviews(extraction_ids: list[str]) -> dict[str, dict]:
    """Return the subset of `extraction_ids` that have an approved review row.

    Used by the export endpoint: the CSV is built from these server-stored
    snapshots, never from client-submitted content.
    """
    if not extraction_ids:
        return {}
    placeholders = ",".join("?" for _ in extraction_ids)
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"SELECT * FROM review_items WHERE approved = 1 AND extraction_id IN ({placeholders})",  # noqa: S608
            extraction_ids,
        ).fetchall()
    return {
        r["extraction_id"]: {
            "edited_response": json.loads(r["edited_response"]),
            "edited_pricing": json.loads(r["edited_pricing"]) if r["edited_pricing"] else None,
            "approved": True,
            "approved_at_utc": r["approved_at_utc"],
            "approved_by": r["approved_by"],
            "updated_at_utc": r["updated_at_utc"],
        }
        for r in rows
    }


def delete_all_reviews() -> int:
    """Wipe review_items (NOT the audit trail). Called when a new extraction
    purges inbound/*.json — review rows for deleted artifacts are meaningless."""
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM review_items")
        conn.commit()
        return cur.rowcount


# --- Exports ----------------------------------------------------------------------

def record_export(
    csv_filename: str,
    row_count: int,
    exported_at_utc: str,
    extraction_ids: list[str],
    actor: str | None,
) -> None:
    """Record one CSV export + an 'exported' audit event per included card."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO exports (csv_filename, row_count, exported_at_utc, actor, extraction_ids)
               VALUES (?,?,?,?,?)""",
            (csv_filename, row_count, exported_at_utc, actor, json.dumps(extraction_ids)),
        )
        for extraction_id in extraction_ids:
            _add_event(conn, extraction_id, "exported", actor, {"csv_filename": csv_filename})
        conn.commit()


# --- Full reset --------------------------------------------------------------------

def clear_all_tables() -> dict[str, int]:
    """Delete every row in every table — the DB half of 'Clear Data'.

    The audit trail goes too: Clear Data is the full-reset button, and keeping
    events about artifacts that no longer exist would just confuse a future
    reader. Returns per-table deletion counts for the response payload.
    """
    counts: dict[str, int] = {}
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Children before parents (extraction_job_images references extraction_jobs).
        for table in (
            "extraction_job_images",
            "extraction_jobs",
            "review_items",
            "review_events",
            "exports",
        ):
            cur = conn.execute(f"DELETE FROM {table}")  # noqa: S608 — fixed table list
            counts[table] = cur.rowcount
        conn.commit()
    return counts
