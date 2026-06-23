import os, re, hashlib
class RedactionLayer:
    patterns=[(re.compile(r"[\w.-]+@[\w.-]+"),"[EMAIL]"),(re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"),"[SSN]"),(re.compile(r"\b(?:\d[ -]*?){13,16}\b"),"[CARD]"),(re.compile(r"(?i)(api[_ -]?key|token|password)\s*[:=]\s*\S+"),"[SECRET]")]
    def redact(self,text:str)->str:
        for p,r in self.patterns: text=p.sub(r,text)
        return text
class ContextCompressor:
    def compress(self,text:str,budget:int=1200)->str: return text if len(text)<=budget else text[:budget//2]+"\n…[compressed]…\n"+text[-budget//2:]
class SemanticSkeletonGenerator:
    def generate(self,text:str)->dict: return {"summary": text[:240], "entities": [], "intents": []}
class Fingerprinter:
    def fingerprint(self,text:str)->str: return hashlib.sha256(text.encode()).hexdigest()
class DriftDetector:
    def drift_score(self,old:str,new:str)->float: return 0.0 if old==new else 1.0
class TokenBudgetEstimator:
    def estimate(self,text:str)->int: return max(1,len(text)//4)
class AxiomRuntimeClient:
    def __init__(self, mode:str|None=None): self.mode=mode or os.getenv("AXIOM_RUNTIME_MODE","deterministic")
    def available(self): return self.mode=="deterministic"
    def compress(self,text:str,budget:int): return ContextCompressor().compress(text,budget)
class AxiomAdapter:
    def __init__(self, mode:str|None=None): self.redactor=RedactionLayer(); self.compressor=ContextCompressor(); self.fingerprinter=Fingerprinter(); self.runtime=AxiomRuntimeClient(mode)
    def package_context(self,text:str,budget:int=1200):
        red=self.redactor.redact(text); compressed=self.runtime.compress(red,budget) if self.runtime.available() else self.compressor.compress(red,budget)
        return {"context":compressed,"fingerprint":self.fingerprinter.fingerprint(red),"tokens_estimated":TokenBudgetEstimator().estimate(red),"runtime_mode":self.runtime.mode,"fallback_used":not self.runtime.available()}
