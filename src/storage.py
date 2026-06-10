"""Persistencia en SQLite: historial de oportunidades + estado del monitor.

Nota Railway: para que el historial sobreviva redeploys, montar un volumen en
`/data` y apuntar DB_PATH=/data/arb.db. Sin volumen, el archivo se reinicia en
cada deploy.
"""

from __future__ import annotations

import time

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    front       TEXT    NOT NULL,   -- 'A' | 'B'
    mode        TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    buy_where   TEXT    NOT NULL,
    sell_where  TEXT    NOT NULL,
    buy_price   REAL    NOT NULL,
    sell_price  REAL    NOT NULL,
    gross_pct   REAL    NOT NULL,
    net_pct     REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opp_ts ON opportunities(ts);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # ── Oportunidades ────────────────────────────────────────────────────────
    async def record_opportunity(self, opp) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT INTO opportunities
               (ts, front, mode, label, buy_where, sell_where,
                buy_price, sell_price, gross_pct, net_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(), opp.front, opp.mode, opp.label,
                opp.buy_where, opp.sell_where, opp.buy_price, opp.sell_price,
                opp.gross_pct, opp.net_pct,
            ),
        )
        await self._db.commit()

    async def recent_opportunities(self, limit: int = 50, front: str | None = None) -> list[dict]:
        assert self._db is not None
        if front:
            cur = await self._db.execute(
                "SELECT * FROM opportunities WHERE front = ? ORDER BY ts DESC LIMIT ?",
                (front, limit),
            )
        else:
            cur = await self._db.execute(
                "SELECT * FROM opportunities ORDER BY ts DESC LIMIT ?", (limit,)
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def count_opportunities_since(self, since_ts: float) -> int:
        assert self._db is not None
        cur = await self._db.execute(
            "SELECT COUNT(*) AS n FROM opportunities WHERE ts >= ?", (since_ts,)
        )
        row = await cur.fetchone()
        return int(row["n"]) if row else 0

    # ── Estado (paused, cooldowns) ───────────────────────────────────────────
    async def _get(self, key: str) -> str | None:
        assert self._db is not None
        cur = await self._db.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def _set(self, key: str, value: str) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self._db.commit()

    async def get_paused(self) -> bool:
        return (await self._get("paused")) == "1"

    async def set_paused(self, paused: bool) -> None:
        await self._set("paused", "1" if paused else "0")

    async def get_last_alert(self, key: str) -> float:
        raw = await self._get(f"last_alert_{key}")
        return float(raw) if raw else 0.0

    async def set_last_alert(self, key: str, ts: float) -> None:
        await self._set(f"last_alert_{key}", str(ts))
