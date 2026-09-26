"""The purse's durable decision ledger — SQLite, not an in-memory counter.

Every payment attempt (approved or refused) is written here. The running
total spent is always *derived* by summing confirmed 'paid' rows fresh from
this table — never cached in a Python variable across the run — so a
restarted process picks up exactly where it left off, and there is no
in-memory number for anything (agent output included) to drift from.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "purse_ledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    seller_url TEXT NOT NULL,
    resource_description TEXT,
    network TEXT,
    asset TEXT,
    quoted_amount_atomic INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('paid', 'refused')),
    reason TEXT NOT NULL,
    tx_hash TEXT
)
"""


@dataclass
class Decision:
    seller_url: str
    resource_description: str | None
    network: str | None
    asset: str | None
    quoted_amount_atomic: int
    decision: str  # 'paid' | 'refused'
    reason: str
    tx_hash: str | None = None


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect():
        pass


def record_decision(d: Decision) -> None:
    if not isinstance(d.quoted_amount_atomic, int):
        raise TypeError("quoted_amount_atomic must be an int (atomic base units)")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO decisions "
            "(seller_url, resource_description, network, asset, quoted_amount_atomic, decision, reason, tx_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                d.seller_url,
                d.resource_description,
                d.network,
                d.asset,
                d.quoted_amount_atomic,
                d.decision,
                d.reason,
                d.tx_hash,
            ),
        )


def total_spent_atomic() -> int:
    """Sum of CONFIRMED paid amounts only — refused/failed attempts never
    count toward spend. Always queried fresh, never cached."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(quoted_amount_atomic), 0) FROM decisions WHERE decision = 'paid'"
        ).fetchone()
        return int(row[0])


def all_decisions() -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM decisions ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]
