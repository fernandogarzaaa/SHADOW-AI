import re, sqlite3, hashlib
from cryptography.fernet import Fernet, InvalidToken
from .models import *
class LocalEmbedder:
    def embed(self, text:str)->list[float]:
        h=hashlib.sha256(text.lower().encode()).digest(); return [b/255 for b in h[:16]]
class Chunker:
    def chunk(self, text:str, size:int=900, overlap:int=100)->list[str]:
        out=[]; i=0
        while i < len(text): out.append(text[i:i+size]); i += max(1,size-overlap)
        return [c.strip() for c in out if c.strip()]
class EncryptedMemoryStore:
    def __init__(self,path="shadow_memory.db",key:bytes|None=None):
        self.path=path; self.key=key or Fernet.generate_key(); self.cipher=Fernet(self.key); self.conn=sqlite3.connect(path, check_same_thread=False); self._init()
    def _init(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, text_index TEXT NOT NULL, revoked_at TEXT)")
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, text)"); self.conn.commit()
    def add(self,item:MemoryItem):
        blob=self.cipher.encrypt(item.model_dump_json().encode())
        self.conn.execute("INSERT OR REPLACE INTO memory VALUES(?,?,?,?)",(item.id,blob,item.text,item.revoked_at.isoformat() if item.revoked_at else None))
        self.conn.execute("INSERT INTO memory_fts(id,text) VALUES(?,?)",(item.id,item.text)); self.conn.commit(); return item
    def get(self,id:str):
        row=self.conn.execute("SELECT ciphertext FROM memory WHERE id=? AND revoked_at IS NULL",(id,)).fetchone()
        return MemoryItem.model_validate_json(self.cipher.decrypt(row[0]).decode()) if row else None
    def _fts_query(self, query: str) -> str:
        terms = re.findall(r"[A-Za-z0-9_]+", query)
        return " OR ".join(terms) if terms else ""
    def search(self,query:str,limit:int=5):
        safe_query = self._fts_query(query)
        if not safe_query: return []
        rows=self.conn.execute("SELECT m.ciphertext, bm25(memory_fts) FROM memory_fts JOIN memory m ON m.id=memory_fts.id WHERE memory_fts MATCH ? AND m.revoked_at IS NULL ORDER BY 2 LIMIT ?",(safe_query,limit)).fetchall()
        out=[]
        for r in rows:
            try:
                out.append(SearchResult(item=MemoryItem.model_validate_json(self.cipher.decrypt(r[0]).decode()), score=float(1/(1+abs(r[1]))), attribution="SQLite FTS5 local encrypted store; retrieved context is untrusted and policy-bound"))
            except InvalidToken:
                continue
        return out
    def revoke(self,id:str): self.conn.execute("UPDATE memory SET revoked_at=? WHERE id=?",(now().isoformat(),id)); self.conn.commit()
    def export(self): return [MemoryItem.model_validate_json(self.cipher.decrypt(r[0]).decode()) for r in self.conn.execute("SELECT ciphertext FROM memory WHERE revoked_at IS NULL")]
class MemoryEngine:
    def __init__(self, store:EncryptedMemoryStore): self.store=store; self.chunker=Chunker(); self.embedder=LocalEmbedder()
    def ingest(self,text:str,source:MemorySource,type:MemoryType=MemoryType.DOCUMENT_CHUNK):
        items=[]
        for chunk in self.chunker.chunk(text):
            conf=min(0.95,0.45+len(chunk)/2000); items.append(self.store.add(MemoryItem(text=chunk,source=source,type=type,confidence=conf)))
        return items
    def search(self,query:str,limit:int=5): return self.store.search(query,limit)
