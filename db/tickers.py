#!/usr/bin/env python3
"""
Description: Ticker CRUD operations for the local SQLite database.
"""
from .database import TickerDatabase
from typing import Optional

class TickerDB:
    @staticmethod
    def upsert(ticker: str, cik: str) -> None:
        """Upsert a single ticker into the database."""
        with TickerDatabase.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tickers (ticker, cik) VALUES (?, ?)",
                (ticker.upper(), cik)
            )
    @staticmethod
    def upsert_many(tickers: list) -> None:
        """Bulk upsert a list of TickerInfo objects."""
        with TickerDatabase.get_connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO tickers (ticker, cik) VALUES (?, ?)",
                [(t.ticker.upper(), t.cik_str) for t in tickers]
            )
    @staticmethod
    def get_cik(ticker: str) -> Optional[str]:
        """Returns CIK for a given ticker, or None if not found."""
        with TickerDatabase.get_connection() as conn:
            row = conn.execute(
                "SELECT cik FROM tickers WHERE ticker = ?",
                (ticker.upper(),)
            ).fetchone()
            return row["cik"] if row else None
    @staticmethod
    def exists(ticker: str) -> bool:
        """Check if a ticker exists in the database."""
        return TickerDB.get_cik(ticker) is not None
    @staticmethod
    def get_all() -> list[dict]:
        """Returns all tickers in the database."""
        with TickerDatabase.get_connection() as conn:
            rows = conn.execute("SELECT ticker, cik FROM tickers").fetchall()
            return [dict(row) for row in rows]