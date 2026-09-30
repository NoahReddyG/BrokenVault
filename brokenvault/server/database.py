import sqlite3
import os
from contextlib import contextmanager
from typing import Generator

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT PRIMARY KEY,
                    source_label TEXT,
                    created_at TEXT NOT NULL,
                    total_logical_bytes INTEGER NOT NULL,
                    uploaded_bytes INTEGER NOT NULL,
                    reused_bytes INTEGER NOT NULL,
                    is_completed INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upload_sessions (
                    upload_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(version_id) REFERENCES versions(version_id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS version_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    FOREIGN KEY(version_id) REFERENCES versions(version_id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    chunk_order INTEGER NOT NULL,
                    chunk_id TEXT NOT NULL,
                    FOREIGN KEY(version_id) REFERENCES versions(version_id) ON DELETE CASCADE,
                    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_chunks_chunk ON file_chunks(chunk_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_chunks_version ON file_chunks(version_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_version_files_version ON version_files(version_id);")
