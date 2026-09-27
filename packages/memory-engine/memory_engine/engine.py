import sqlite3, hashlib, hmac, math, re
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from .models import *
class LocalEmbedder:
    def embed(self, text:str)->list[float]:
        h=hashlib.sha256(text.lower().encode()).digest(); return [b/255 for b in h[:16]]
class Chunker:
    def chunk(self, text:str, size:int=900, overlap:int=100)->list[str]:
        out=[]; i=0
        while i < len(text): out.append(text[i:i+size]); i += max(1,size-overlap)
        return [c.strip() for c in out if c.strip()]
def content_hash(text:str, source_id:str="")->str: return hashlib.sha256((source_id+"\n"+text.strip().lower()).encode()).hexdigest()
def freshness_score(created_at:datetime)->float:
    age_days=max(0.0,(datetime.now(timezone.utc)-created_at).total_seconds()/86400); return round(1/(1+age_days/30),4)
def classify_category(text:str, source:MemorySource)->MemoryCategory:
    low=(source.title+" "+text).lower()
    if any(w in low for w in ["secret","password","ssn","token","api key"]): return MemoryCategory.SENSITIVE
    if "project" in low: return MemoryCategory.PROJECT
    if "profile" in low or "preference" in low: return MemoryCategory.PROFILE
    return MemoryCategory.CONNECTOR if source.kind!="manual" else MemoryCategory.NOTE
class EncryptedMemoryStore:
    # FTS index format version. "blind-v2" stores HMAC blind-index tokens
    # instead of raw text; anything else is rebuilt from the encrypted
    # blobs on open (healing databases written by older formats).
    FTS_INDEX_VERSION = "blind-v2"

    def __init__(self,path="shadow_memory.db",key:bytes|None=None):
        self.path=path; self.key=key or Fernet.generate_key(); self.cipher=Fernet(self.key); self.conn=sqlite3.connect(path, check_same_thread=False)
        # Separate index key, domain-separated from the encryption key.
        # A leaked index reveals only token equality and counts, never terms.
        self.index_key=hmac.new(self.key, b"shadow-memory-fts-v2", hashlib.sha256).digest()
        self._init()

    def _blind_token(self, term:str)->str:
        return hmac.new(self.index_key, term.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _terms(text:str)->list[str]:
        return [t.lower() for t in re.findall(r'[A-Za-z0-9_]+', text)]

    def _blind_index_text(self, text:str)->str:
        return " ".join(self._blind_token(t) for t in self._terms(text))

    def _init(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, source_id TEXT, content_hash TEXT UNIQUE, ciphertext BLOB NOT NULL, text_index TEXT NOT NULL, revoked_at TEXT)")
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, text)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        self.conn.commit()
        self._ensure_blind_index()

    def _ensure_blind_index(self):
        row=self.conn.execute("SELECT value FROM meta WHERE key='fts_version'").fetchone()
        if row and row[0]==self.FTS_INDEX_VERSION: return
        # Rebuild the index from the encrypted blobs so databases written
        # by the old plaintext-index format stop leaking memory contents.
        self.conn.execute("DELETE FROM memory_fts")
        for item_id, blob in self.conn.execute("SELECT id, ciphertext FROM memory WHERE revoked_at IS NULL").fetchall():
            try: item=MemoryItem.model_validate_json(self.cipher.decrypt(blob).decode())
            except Exception: continue  # wrong key or corrupt row: leave unindexed
            blind=self._blind_index_text(item.text)
            self.conn.execute("INSERT INTO memory_fts(id,text) VALUES(?,?)",(item_id, blind))
            self.conn.execute("UPDATE memory SET text_index=? WHERE id=?",(blind, item_id))
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts_version',?)",(self.FTS_INDEX_VERSION,))
        self.conn.commit()
    def add(self,item:MemoryItem):
        item.content_hash=item.content_hash or content_hash(item.text,item.source.id)
        existing=self.conn.execute("SELECT id,ciphertext FROM memory WHERE content_hash=? AND revoked_at IS NULL",(item.content_hash,)).fetchone()
        if existing: return MemoryItem.model_validate_json(self.cipher.decrypt(existing[1]).decode())
        blob=self.cipher.encrypt(item.model_dump_json().encode())
        blind=self._blind_index_text(item.text)
        self.conn.execute("INSERT OR REPLACE INTO memory VALUES(?,?,?,?,?,?)",(item.id,item.source.id,item.content_hash,blob,blind,item.revoked_at.isoformat() if item.revoked_at else None))
        self.conn.execute("INSERT INTO memory_fts(id,text) VALUES(?,?)",(item.id,blind)); self.conn.commit(); return item
    def get(self,id:str):
        row=self.conn.execute("SELECT ciphertext FROM memory WHERE id=? AND revoked_at IS NULL",(id,)).fetchone()
        return MemoryItem.model_validate_json(self.cipher.decrypt(row[0]).decode()) if row else None
    def search(self,query:str,limit:int=5, include_sensitive:bool=True):
        tokens=[self._blind_token(t) for t in self._terms(query)]
        if not tokens: return []
        safe_query=' OR '.join(tokens)
        rows=self.conn.execute("SELECT m.ciphertext, bm25(memory_fts) FROM memory_fts JOIN memory m ON m.id=memory_fts.id WHERE memory_fts MATCH ? AND m.revoked_at IS NULL ORDER BY 2 LIMIT ?",(safe_query,limit*3)).fetchall()
        out=[]
        for blob,bm in rows:
            item=MemoryItem.model_validate_json(self.cipher.decrypt(blob).decode())
            if item.sensitive and not include_sensitive: continue
            fresh=freshness_score(item.created_at); score=float(1/(1+abs(bm)))
            out.append(SearchResult(item=item,score=score,freshness=fresh,attribution=f"{item.source.title} ({item.source.kind})",explanation=f"Matched local FTS terms from source '{item.source.title}' with confidence {item.confidence:.2f} and freshness {fresh:.2f}."))
            if len(out)>=limit: break
        return out
    def revoke(self,id:str): self.conn.execute("UPDATE memory SET revoked_at=? WHERE id=?",(now().isoformat(),id)); self.conn.commit()
    def delete_by_source(self,source_id:str):
        self.conn.execute("UPDATE memory SET revoked_at=? WHERE source_id=?",(now().isoformat(),source_id)); self.conn.commit()
    def export(self,include_sensitive:bool=False):
        items=[MemoryItem.model_validate_json(self.cipher.decrypt(r[0]).decode()) for r in self.conn.execute("SELECT ciphertext FROM memory WHERE revoked_at IS NULL")]
        return [i for i in items if include_sensitive or not i.sensitive]
    def recent(self,limit:int=50,offset:int=0,include_sensitive:bool=False):
        """Newest-first paginated items for memory cards. Sorted in Python:
        created_at lives inside the encrypted blob, and we do not add a
        plaintext timestamp column (no new metadata leaks). Returns
        (page_items, total_matching)."""
        limit=max(1,min(limit,200)); offset=max(0,offset)
        items=[MemoryItem.model_validate_json(self.cipher.decrypt(r[0]).decode()) for r in self.conn.execute("SELECT ciphertext FROM memory WHERE revoked_at IS NULL")]
        items=[i for i in items if include_sensitive or not i.sensitive]
        items.sort(key=lambda i:i.created_at,reverse=True)
        return items[offset:offset+limit],len(items)
class MemoryEngine:
    def __init__(self, store:EncryptedMemoryStore): self.store=store; self.chunker=Chunker(); self.embedder=LocalEmbedder()
    def ingest(self,text:str,source:MemorySource,type:MemoryType=MemoryType.DOCUMENT_CHUNK,sensitive:bool|None=None,do_not_send_to_cloud:bool|None=None):
        items=[]
        category=classify_category(text,source); sens=sensitive if sensitive is not None else category==MemoryCategory.SENSITIVE
        for chunk in self.chunker.chunk(text):
            conf=min(0.95,0.45+len(chunk)/2000); items.append(self.store.add(MemoryItem(text=chunk,source=source,type=type,category=category,confidence=conf,sensitive=sens,do_not_send_to_cloud=(do_not_send_to_cloud if do_not_send_to_cloud is not None else sens))))
        return items
    def search(self,query:str,limit:int=5,include_sensitive:bool=True): return self.store.search(query,limit,include_sensitive)
    def delete_by_source(self,source_id:str): return self.store.delete_by_source(source_id)
    def export(self,include_sensitive:bool=False): return self.store.export(include_sensitive)
    def recent(self,limit:int=50,offset:int=0,include_sensitive:bool=False): return self.store.recent(limit,offset,include_sensitive)
