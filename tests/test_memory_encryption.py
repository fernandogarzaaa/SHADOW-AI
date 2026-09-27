"""Regression tests for encrypted memory search (audit P0-5).

The FTS keyword index must never contain plaintext: it stores HMAC
blind-index tokens. Databases written by the old plaintext-index format
are rebuilt from the encrypted blobs on open.
"""
import sqlite3
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from memory_engine import EncryptedMemoryStore, MemoryEngine
from memory_engine.models import MemoryItem, MemorySource


def _engine(path, key=None):
    return MemoryEngine(EncryptedMemoryStore(path=str(path), key=key))


def _source(title="t"):
    return MemorySource(kind="manual", title=title)


def test_no_plaintext_in_db_file(tmp_path):
    db = tmp_path / "mem.db"
    eng = _engine(db)
    eng.ingest("the zebra vault combination is 49-50-51", _source("s"))
    eng.store.conn.commit()
    eng.store.conn.close()
    raw = db.read_bytes()
    assert b"zebra vault combination" not in raw
    assert b"49-50-51" not in raw


def test_search_roundtrip_over_blind_index(tmp_path):
    eng = _engine(tmp_path / "mem.db")
    eng.ingest("the zebra vault combination is secret", _source("s"))
    res = eng.search("zebra vault")
    assert len(res) == 1
    assert "zebra" in res[0].item.text


def test_search_is_case_insensitive(tmp_path):
    eng = _engine(tmp_path / "mem.db")
    eng.ingest("Hello World note", _source("s"))
    assert len(eng.search("hello")) == 1
    assert len(eng.search("WORLD")) == 1


def test_search_with_no_terms_returns_empty_not_500(tmp_path):
    eng = _engine(tmp_path / "mem.db")
    eng.ingest("some content here", _source("s"))
    assert eng.search("!!!") == []


def test_old_plaintext_db_is_healed_on_open(tmp_path):
    db = tmp_path / "old.db"
    key = Fernet.generate_key()
    item = MemoryItem(text="the zebra vault combination is 49-50-51",
                      source=_source("s"))
    blob = Fernet(key).encrypt(item.model_dump_json().encode())
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memory(id TEXT PRIMARY KEY, source_id TEXT, content_hash TEXT UNIQUE, ciphertext BLOB NOT NULL, text_index TEXT NOT NULL, revoked_at TEXT)")
    conn.execute("CREATE VIRTUAL TABLE memory_fts USING fts5(id UNINDEXED, text)")
    conn.execute("INSERT INTO memory VALUES(?,?,?,?,?,?)",
                 (item.id, item.source.id, "h", blob, item.text, None))
    conn.execute("INSERT INTO memory_fts(id,text) VALUES(?,?)", (item.id, item.text))
    conn.commit(); conn.close()
    assert b"zebra" in db.read_bytes()  # old format really leaks

    store = EncryptedMemoryStore(path=str(db), key=key)
    fts_text = store.conn.execute("SELECT text FROM memory_fts").fetchone()[0]
    assert "zebra" not in fts_text  # rebuilt as blind tokens
    cols = store.conn.execute("SELECT text_index FROM memory").fetchone()[0]
    assert "zebra" not in cols
    # Search still works after the rebuild.
    eng = MemoryEngine(store)
    assert len(eng.search("zebra")) == 1


def test_wrong_key_leaves_index_empty_without_crash(tmp_path):
    db = tmp_path / "mem.db"
    eng = _engine(db)
    eng.ingest("the zebra vault combination", _source("s"))
    eng.store.conn.close()
    store2 = EncryptedMemoryStore(path=str(db))  # fresh random key
    assert MemoryEngine(store2).search("zebra") == []
