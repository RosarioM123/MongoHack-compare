"""Persistence layer: MongoDB Atlas first, SQLite fallback for dev.

Same tiny interface either way: ``save`` / ``find`` / ``find_one`` /
``clear`` over the 11 developmental collections. Set ``MONGODB_URI`` (the
hackathon Sandbox URI) to use Atlas; otherwise everything runs locally with
zero setup.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((jsonable(v) for v in obj), key=repr)
    return obj


class SQLiteBackend:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def _table(self, coll: str) -> str:
        if not coll.replace("_", "").isalnum():
            raise ValueError(f"bad collection name: {coll}")
        self.conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{coll}" (id TEXT PRIMARY KEY, doc TEXT)'
        )
        return coll

    def save(self, coll: str, doc: Dict[str, Any]) -> str:
        table = self._table(coll)
        doc = dict(jsonable(doc))
        doc_id = str(doc.get("_id") or doc.get("trace_id")
                    or doc.get("mutation_id") or doc.get("version_id")
                    or uuid.uuid4().hex)
        doc["_id"] = doc_id
        self.conn.execute(
            f'INSERT OR REPLACE INTO "{table}" (id, doc) VALUES (?, ?)',
            (doc_id, json.dumps(doc)),
        )
        self.conn.commit()
        return doc_id

    def _matches(self, doc: Dict[str, Any], query: Optional[Dict]) -> bool:
        if not query:
            return True
        return all(doc.get(k) == v for k, v in query.items())

    def find(self, coll: str, query: Optional[Dict] = None,
             limit: int = 500) -> List[Dict[str, Any]]:
        table = self._table(coll)
        rows = self.conn.execute(f'SELECT doc FROM "{table}" LIMIT ?', (limit,))
        docs = [json.loads(r["doc"]) for r in rows]
        return [d for d in docs if self._matches(d, query)][:limit]

    def find_one(self, coll: str, query: Dict) -> Optional[Dict[str, Any]]:
        docs = self.find(coll, query, limit=500)
        return docs[0] if docs else None

    def clear(self, coll: str) -> None:
        table = self._table(coll)
        self.conn.execute(f'DELETE FROM "{table}"')
        self.conn.commit()


class MongoBackend:
    def __init__(self, uri: str, db_name: str):
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        self.db = self.client[db_name]
        # Fail fast if Atlas is unreachable so the caller can fall back.
        self.client.admin.command("ping")

    def save(self, coll: str, doc: Dict[str, Any]) -> str:
        doc = dict(jsonable(doc))
        doc["_id"] = str(doc.get("_id") or doc.get("trace_id")
                         or doc.get("mutation_id") or doc.get("version_id")
                         or uuid.uuid4().hex)
        self.db[coll].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return doc["_id"]

    def find(self, coll: str, query: Optional[Dict] = None,
             limit: int = 500) -> List[Dict[str, Any]]:
        docs = list(self.db[coll].find(query or {}).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    def find_one(self, coll: str, query: Dict) -> Optional[Dict[str, Any]]:
        doc = self.db[coll].find_one(query)
        if doc is not None:
            doc["_id"] = str(doc["_id"])
        return doc

    def clear(self, coll: str) -> None:
        self.db[coll].delete_many({})


def get_db():
    """Atlas when MONGODB_URI is set and reachable, else local SQLite."""
    uri = os.environ.get("MONGODB_URI")
    if uri:
        try:
            db_name = os.environ.get("MONGODB_DATABASE", "cookmemory")
            backend = MongoBackend(uri, db_name)
            backend.backend_name = f"atlas:{db_name}"  # type: ignore[attr-defined]
            return backend
        except Exception as exc:  # noqa: BLE001 - fall back loudly
            print(f"[db] Atlas unreachable ({exc}); falling back to SQLite.")
    path = os.environ.get("DEV_DB", "work/dev.sqlite")
    backend = SQLiteBackend(path)
    backend.backend_name = f"sqlite:{path}"  # type: ignore[attr-defined]
    return backend
