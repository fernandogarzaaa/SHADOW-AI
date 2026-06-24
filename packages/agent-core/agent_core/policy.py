from .models import *
SENSITIVE_TOOLS={"send_email","send_message","delete_file","write_file","device_control","cloud_model"}
BLOCKED_TOOLS={"keylogger","covert_monitor","bypass_ios_sandbox","silent_microphone","silent_camera"}
class PolicyEngine:
    def classify_action(self, action: AgentAction) -> RiskClass:
        n=action.tool_name.lower(); d=action.description.lower()
        if n in BLOCKED_TOOLS or any(x in d for x in ["keylog","covert","bypass ios","silently record"]): return RiskClass.BLOCKED
        if n in {"delete_file","send_email","send_message","device_control"}: return RiskClass.CRITICAL
        if n in SENSITIVE_TOOLS or "cloud" in d: return RiskClass.HIGH
        if any(w in d for w in ["calendar","email","contact","personal"]): return RiskClass.MEDIUM
        return RiskClass.LOW
    def requires_approval(self, action: AgentAction, profile: UserProfile) -> bool:
        risk=self.classify_action(action)
        if profile.emergency_paused or profile.autonomy_mode in [AutonomyMode.OFF, AutonomyMode.SUGGEST_ONLY, AutonomyMode.DRAFT_ONLY]: return True
        if risk in [RiskClass.MEDIUM,RiskClass.HIGH,RiskClass.CRITICAL,RiskClass.BLOCKED]: return True
        return profile.autonomy_mode != AutonomyMode.TRUSTED_WORKFLOW
    def can_execute(self, action: AgentAction, profile: UserProfile, approved: bool=False) -> tuple[bool,str]:
        risk=self.classify_action(action)
        if profile.emergency_paused: return False,"Emergency pause is enabled."
        if risk==RiskClass.BLOCKED: return False,"Action is blocked by hard safety policy."
        if self.requires_approval(action, profile) and not approved: return False,"Approval required before execution."
        return True,"Allowed."
    def cloud_allowed(self, grants:list[ConsentGrant], explicit_approval:bool) -> bool:
        return explicit_approval and any(g.model_access_level!="local_only" and g.revoked_at is None for g in grants)
