"""SQLite sink plugin — reference implementation for SinkPlugin."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from canarchy.plugins import CANARCHY_API_VERSION


class SqliteSinkPlugin:
    """Write CANarchy command payloads to a SQLite database."""

    name = "sqlite-sink"
    api_version = CANARCHY_API_VERSION
    supported_formats = ["json"]

    def write(
        self,
        payload: dict[str, Any],
        destination: str,
        *,
        output_format: str = "json",
    ) -> dict[str, Any]:
        """Insert frame events from *payload* into a SQLite DB at *destination*.

        Creates the database and ``frames`` table if they do not exist.
        Returns a dict with ``destination`` and ``rows_written``.
        """
        con = sqlite3.connect(destination)
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS frames (
                    id      INTEGER PRIMARY KEY,
                    ts      REAL,
                    command TEXT,
                    payload TEXT
                )
                """
            )
            con.commit()

            command = payload.get("command", "")
            events = payload.get("data", {}).get("events", [])

            rows_written = 0
            if events:
                for event in events:
                    ts = event.get("ts", time.time())
                    con.execute(
                        "INSERT INTO frames (ts, command, payload) VALUES (?, ?, ?)",
                        (ts, command, json.dumps(event)),
                    )
                    rows_written += 1
            else:
                # Fall back to inserting the payload itself as a single row
                ts = time.time()
                con.execute(
                    "INSERT INTO frames (ts, command, payload) VALUES (?, ?, ?)",
                    (ts, command, json.dumps(payload)),
                )
                rows_written = 1

            con.commit()
        finally:
            con.close()

        return {"destination": destination, "rows_written": rows_written}
