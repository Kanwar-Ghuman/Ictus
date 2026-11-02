"""Crash-safe reservations; a timed-out order keeps its budget until reconciled."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from octagon.trading.risk import decimal, money

MICROS = Decimal("1000000")


def units(value: Decimal) -> int:
    scaled = value * MICROS
    if not value.is_finite() or value < 0 or scaled != scaled.to_integral_value():
        raise ValueError("Invalid dollar precision")
    return int(scaled)


def dollars(value: int) -> str:
    return format(Decimal(value) / MICROS, "f")


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, event_id TEXT NOT NULL, mode TEXT NOT NULL,
                    card_slug TEXT NOT NULL, budget INTEGER NOT NULL CHECK(budget > 0),
                    config TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(event_id, mode)
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    bout_id TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL,
                    count INTEGER NOT NULL, price TEXT NOT NULL, reserved INTEGER NOT NULL,
                    spent INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
                    exchange_order_id TEXT, filled_count TEXT NOT NULL DEFAULT '0',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(session_id, bout_id)
                );
                CREATE TABLE IF NOT EXISTS blocked_bouts (
                    session_id TEXT NOT NULL REFERENCES sessions(id), bout_id TEXT NOT NULL,
                    reason TEXT NOT NULL, PRIMARY KEY(session_id, bout_id)
                );
                CREATE TABLE IF NOT EXISTS active_sessions (
                    mode TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id)
                );
            """)
            self._migrate_attempt_keys(db)

    @staticmethod
    def _migrate_attempt_keys(db):
        """Older journals allowed one order per ticker. In-fight trading keys
        attempts by bout *and* round break, so only UNIQUE(session_id, bout_id)
        remains. Rebuilt in one transaction; rows are copied unchanged."""
        sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()[0]
        if "UNIQUE(session_id, ticker)" not in sql:
            return
        db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE orders_migrated (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                bout_id TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL,
                count INTEGER NOT NULL, price TEXT NOT NULL, reserved INTEGER NOT NULL,
                spent INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
                exchange_order_id TEXT, filled_count TEXT NOT NULL DEFAULT '0',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, bout_id)
            );
            INSERT INTO orders_migrated SELECT * FROM orders;
            DROP TABLE orders;
            ALTER TABLE orders_migrated RENAME TO orders;
            COMMIT;
        """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def configure(self, config: dict, mode: str) -> str:
        budget = units(money(config["budget_dollars"]))
        if budget <= 0:
            raise ValueError("Event budget must be greater than zero")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM sessions WHERE event_id=? AND mode=?",
                (config["espn_event_id"], mode),
            ).fetchone()
            if old:
                used = db.execute(
                    "SELECT COALESCE(SUM(spent + reserved),0) FROM orders WHERE session_id=?",
                    (old["id"],),
                ).fetchone()[0]
                if budget < used:
                    raise ValueError("Budget cannot be below spent plus reserved funds")
                old_config = json.loads(old["config"])
                # Fights with an order attempt (pre-fight "<bout>" or in-fight
                # "<bout>:r<k>") keep their exact mapping and forecast; other
                # fights may be added or dropped.
                attempted = {row[0].split(":")[0] for row in db.execute(
                    "SELECT bout_id FROM orders WHERE session_id=?", (old["id"],))}
                if attempted:
                    before = {m["bout_id"]: m for m in old_config["mappings"]}
                    after = {m["bout_id"]: m for m in config["mappings"]}
                    if config["card_slug"] != old["card_slug"] or any(
                        after.get(bout) != before[bout] for bout in attempted if bout in before
                    ):
                        raise ValueError("A fight that already has a bet keeps its original "
                                         "market and forecast")
                db.execute("UPDATE sessions SET budget=?,config=?,card_slug=? WHERE id=?",
                           (budget, json.dumps(config), config["card_slug"], old["id"]))
                db.execute("INSERT OR REPLACE INTO active_sessions VALUES(?,?)", (mode, old["id"]))
                return old["id"]
            session_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO sessions(id,event_id,mode,card_slug,budget,config) VALUES(?,?,?,?,?,?)",
                (session_id, config["espn_event_id"], mode, config["card_slug"], budget,
                 json.dumps(config)),
            )
            db.execute("INSERT OR REPLACE INTO active_sessions VALUES(?,?)", (mode, session_id))
            return session_id

    def latest(self, mode: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT s.* FROM sessions s JOIN active_sessions a "
                             "ON s.id=a.session_id WHERE a.mode=?", (mode,)).fetchone()
            return dict(row) if row else None

    def event(self, session_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown trading session")
            spent, reserved = db.execute(
                "SELECT COALESCE(SUM(spent),0),COALESCE(SUM(reserved),0) "
                "FROM orders WHERE session_id=?", (session_id,),
            ).fetchone()
        return {
            "session_id": session_id, "event_id": row["event_id"], "card_slug": row["card_slug"],
            "budget_dollars": dollars(row["budget"]), "spent_dollars": dollars(spent),
            "reserved_dollars": dollars(reserved),
            "remaining_dollars": dollars(max(0, row["budget"] - spent - reserved)),
        }

    def orders(self, session_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM orders WHERE session_id=? ORDER BY rowid DESC",
                              (session_id,)).fetchall()
        return [dict(row) | {"price_dollars": row["price"],
                             "cost_dollars": dollars(row["spent"]),
                             "reserved_dollars": dollars(row["reserved"])} for row in rows]

    def block_bout(self, session_id: str, bout_id: str, reason: str):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO blocked_bouts VALUES(?,?,?)",
                       (session_id, bout_id, reason))

    def blocked(self, session_id: str, bout_id: str) -> str | None:
        with self.connection() as db:
            row = db.execute("SELECT reason FROM blocked_bouts WHERE session_id=? AND bout_id=?",
                             (session_id, bout_id)).fetchone()
        return row[0] if row else None

    def reserve(self, session_id: str, bout_id: str, ticker: str, candidate) -> str:
        amount = units(candidate.reserved_cost)
        if candidate.count <= 0 or amount <= 0:
            raise ValueError("Cannot reserve an empty order")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            budget = db.execute("SELECT budget FROM sessions WHERE id=?",
                                (session_id,)).fetchone()[0]
            used = db.execute("SELECT COALESCE(SUM(spent+reserved),0) FROM orders "
                              "WHERE session_id=?", (session_id,)).fetchone()[0]
            if used + amount > budget:
                raise ValueError("Event budget exhausted")
            if db.execute("SELECT 1 FROM orders WHERE session_id=? AND reserved>0 LIMIT 1",
                          (session_id,)).fetchone():
                raise ValueError("Another order needs reconciliation before spending more")
            if db.execute("SELECT 1 FROM blocked_bouts WHERE session_id=? AND bout_id=?",
                          (session_id, bout_id.split(":")[0])).fetchone():
                raise ValueError("Bout has already started or become unavailable")
            client_id = str(uuid.uuid4())
            try:
                db.execute(
                    "INSERT INTO orders(id,session_id,bout_id,ticker,side,count,price,reserved,status) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (client_id, session_id, bout_id, ticker, candidate.side, candidate.count,
                     str(candidate.price), amount, "pending"),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("This attempt is already recorded; reconcile it first") from exc
        return client_id

    def mark_unknown(self, client_id: str, exchange_order_id: str | None = None):
        with self.connection() as db:
            db.execute("UPDATE orders SET status='unknown',exchange_order_id="
                       "COALESCE(?,exchange_order_id) WHERE id=? AND reserved>0",
                       (exchange_order_id, client_id))

    def finish(self, client_id: str, spent: Decimal, filled_count: Decimal, status: str,
               exchange_order_id: str | None = None):
        amount = units(spent)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM orders WHERE id=?", (client_id,)).fetchone()
            if not row or row["status"] not in {"pending", "unknown"}:
                raise ValueError("Order is not awaiting reconciliation")
            if not decimal(filled_count).is_finite() or not 0 <= filled_count <= row["count"]:
                raise ValueError("Invalid reconciled fill count")
            if amount > row["reserved"]:
                raise ValueError("Exchange charge exceeds reservation; manual review required")
            db.execute("UPDATE orders SET spent=?,reserved=0,status=?,filled_count=?,"
                       "exchange_order_id=? WHERE id=?",
                       (amount, status, str(filled_count), exchange_order_id, client_id))
