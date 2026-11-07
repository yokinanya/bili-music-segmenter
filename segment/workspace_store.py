"""Transactional documents for the local workspace and shared audio cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class DocumentStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS documents "
                "(collection TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(collection, id))"
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, collection: str, identity: str) -> dict:
        with self.connect() as connection:
            return self._get(connection, collection, identity)

    @staticmethod
    def _get(connection, collection: str, identity: str) -> dict:
        row = connection.execute(
            "SELECT body FROM documents WHERE collection=? AND id=?", (collection, identity)
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row[0])

    @contextmanager
    def transaction(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield _Transaction(connection)

    def list(self, collection: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM documents WHERE collection=? ORDER BY rowid", (collection,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, collection: str, document: dict) -> None:
        with self.connect() as connection:
            self._put(connection, collection, document)

    def update(self, collection: str, identity: str, change: Callable[[dict], dict]) -> dict:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            document = change(self._get(connection, collection, identity))
            self._put(connection, collection, document)
            return document

    def delete(self, collection: str, identity: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM documents WHERE collection=? AND id=?", (collection, identity))

    @staticmethod
    def _put(connection: sqlite3.Connection, collection: str, document: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO documents(collection,id,body) VALUES(?,?,?) "
            "ON CONFLICT(collection,id) DO UPDATE SET body=excluded.body",
            (collection, document["id"], json.dumps(document, ensure_ascii=False, allow_nan=False)),
        )


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def get(self, collection: str, identity: str) -> dict:
        return DocumentStore._get(self.connection, collection, identity)

    def put(self, collection: str, document: dict) -> None:
        DocumentStore._put(self.connection, collection, document)
