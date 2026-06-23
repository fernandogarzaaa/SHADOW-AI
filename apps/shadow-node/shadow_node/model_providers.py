import os
class ModelProviderConfig:
    def __init__(self):
        self.cloud_enabled=os.getenv("SHADOW_CLOUD_ENABLED","false").lower()=="true"; self.provider=os.getenv("SHADOW_MODEL_PROVIDER","local_mock"); self.endpoint=os.getenv("SHADOW_MODEL_ENDPOINT",""); self.api_key_env=os.getenv("SHADOW_MODEL_API_KEY_ENV","")
    def safe_summary(self): return {"cloud_enabled":self.cloud_enabled,"provider":self.provider,"endpoint_configured":bool(self.endpoint),"api_key_configured":bool(self.api_key_env and os.getenv(self.api_key_env))}
class LocalMockModel:
    def complete(self,prompt:str,context:str=""): return "Local mock answer based on approved local context."
