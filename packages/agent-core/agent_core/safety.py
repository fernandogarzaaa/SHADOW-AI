import re
PROMPT_INJECTION_PATTERNS=[r"ignore (all )?(previous|system|policy)", r"reveal (the )?(secret|api key|token)", r"bypass consent", r"send .* without approval", r"exfiltrate", r"override safety"]
SECRET_REQUEST_PATTERNS=[r"reveal .*secret", r"reveal .*api key", r"show .*api key", r"dump .*token", r"bypass .*consent", r"ignore .*policy"]
def detect_prompt_injection(text:str)->list[str]:
    low=text.lower(); return [p for p in PROMPT_INJECTION_PATTERNS if re.search(p, low)]
def is_suspicious_user_request(text:str)->bool:
    low=text.lower(); return any(re.search(p,low) for p in SECRET_REQUEST_PATTERNS)
def mark_untrusted(text:str)->str: return f"UNTRUSTED_CONTEXT_START\n{text}\nUNTRUSTED_CONTEXT_END"
