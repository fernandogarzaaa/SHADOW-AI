from pathlib import Path
SUPPORTED={".txt",".md",".markdown",".json"}
def read_local_document(path:str)->tuple[str,str]:
    p=Path(path)
    if p.suffix.lower() not in SUPPORTED: raise ValueError(f"unsupported_file_type:{p.suffix}")
    if not p.exists() or not p.is_file(): raise FileNotFoundError(path)
    return p.read_text(encoding="utf-8"), p.suffix.lower().lstrip('.') or 'text'
