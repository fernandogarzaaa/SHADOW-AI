from pathlib import Path
SUPPORTED={".txt",".md",".markdown",".json"}
# Refuse to read more than this in a single ingest: memory items are text and
# the FTS index is not built for multi-megabyte blobs (audit P0-6).
MAX_FILE_BYTES=5*1024*1024
def read_local_document(path:str, allowed_roots:list|None=None)->tuple[str,str]:
    p=Path(path)
    if p.suffix.lower() not in SUPPORTED: raise ValueError(f"unsupported_file_type:{p.suffix}")
    # Resolve symlinks and ".." BEFORE any check: every check below applies to
    # the real file that would actually be read (audit P0-6).
    rp=p.resolve()
    if not rp.is_file(): raise FileNotFoundError(path)
    roots=[Path(r).resolve() for r in (allowed_roots or [])]
    if not roots or not any(rp==r or r in rp.parents for r in roots):
        raise PermissionError(f"path outside allowed ingest roots: {path}")
    if rp.stat().st_size>MAX_FILE_BYTES: raise ValueError(f"file_too_large:{rp.stat().st_size}")
    return rp.read_text(encoding="utf-8"), rp.suffix.lower().lstrip('.') or 'text'
