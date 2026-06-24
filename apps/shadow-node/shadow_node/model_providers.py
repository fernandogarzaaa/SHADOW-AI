from __future__ import annotations
from dataclasses import dataclass
from axiom_adapter import AxiomAdapter
from agent_core import ConsentGrant
@dataclass
class ModelRequest:
    prompt: str; context: str; provider: str="local_mock"; explicit_cloud_approval: bool=False
class ModelProvider:
    name="base"; cloud=False
    def complete(self, req: ModelRequest) -> dict: raise NotImplementedError
class LocalMockModelProvider(ModelProvider):
    name="local_mock"; cloud=False
    def complete(self, req): return {"provider":self.name,"text":f"Local answer based on approved context: {req.context[:180]}","cloud_used":False}
class OpenAICompatibleProvider(ModelProvider):
    name="openai_compatible"; cloud=True
    def complete(self, req): return {"provider":self.name,"text":"OpenAI-compatible provider interface not invoked without configured secret and consent.","cloud_used":True}
class OpenRouterCompatibleProvider(OpenAICompatibleProvider): name="openrouter_compatible"
class LocalModelProvider(LocalMockModelProvider): name="local_model_placeholder"
class ModelProviderRegistry:
    def __init__(self): self.providers={p.name:p for p in [LocalMockModelProvider(),OpenAICompatibleProvider(),OpenRouterCompatibleProvider(),LocalModelProvider()]}; self.axiom=AxiomAdapter()
    def complete(self, req: ModelRequest, consents: list[ConsentGrant]) -> dict:
        provider=self.providers[req.provider]
        package=self.axiom.package_context(req.context)
        package["semantic_skeleton"]=self.axiom.skeleton.generate(package["context"]) if hasattr(self.axiom,"skeleton") else {"summary":package["context"][:240],"entities":[],"intents":[]}
        if provider.cloud and not (req.explicit_cloud_approval and any(c.model_access_level != "local_only" and c.revoked_at is None for c in consents)):
            return {"blocked":True,"reason":"Cloud model use requires explicit approval and non-local consent grant.","context_package":package}
        res=provider.complete(req); res["context_package"]=package; return res
