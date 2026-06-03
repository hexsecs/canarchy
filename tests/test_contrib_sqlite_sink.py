"""Tests for the reference SQLite-sink contrib plugin."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the repo root is on sys.path so `contrib` can be imported as a package.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from canarchy.plugins import SinkPlugin  # noqa: E402
from contrib.plugins.sqlite_sink.plugin import SqliteSinkPlugin  # noqa: E402


class SqliteSinkPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = SqliteSinkPlugin()

    def test_sqlite_sink_writes_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "out.db")
            payload = {
                "command": "capture",
                "data": {
                    "events": [
                        {"type": "frame", "ts": 1.0},
                        {"type": "frame", "ts": 2.0},
                    ]
                },
            }
            result = self.plugin.write(payload, db_path)
            self.assertEqual(result["rows_written"], 2)
            self.assertEqual(result["destination"], db_path)

            con = sqlite3.connect(db_path)
            rows = con.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
            con.close()
            self.assertEqual(rows, 2)

    def test_sqlite_sink_creates_db_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "subdir", "new.db")
            os.makedirs(os.path.dirname(db_path))
            payload = {
                "command": "capture",
                "data": {"events": [{"type": "frame", "ts": 0.5}]},
            }
            self.plugin.write(payload, db_path)
            self.assertTrue(os.path.exists(db_path))

    def test_sqlite_sink_interface_check(self) -> None:
        self.assertIsInstance(self.plugin, SinkPlugin)
