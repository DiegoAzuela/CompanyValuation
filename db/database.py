#!/usr/bin/env python3
"""
Description: This module initializes the local SQLite database and provides utility functions for database operations.
"""

import sqlite3
from pathlib import Path

class TickerDatabase:
    DB_PATH = Path(__file__).parent.parent / "storage" / "tickers.db"
    @staticmethod
    def get_connection() -> sqlite3.Connection:
        """Returns a connection to the local SQLite database."""
        conn = sqlite3.connect(TickerDatabase.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    @staticmethod
    def init_db() -> None:
        """Initializes the database and creates tables if they don't exist."""
        with TickerDatabase.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tickers (
                    ticker TEXT PRIMARY KEY,
                    cik TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)