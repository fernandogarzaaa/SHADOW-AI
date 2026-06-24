from .models import *
SENSITIVE_TOOLS={"send_email","send_message","write_file","device_control","cloud_model","ghost_handoff"}
DESTRUCTIVE_TOOLS={"delete_file","overwrite_file","shell_rm"}
BLOCKED_TOOLS={"keylogger","covert_monitor","bypass_ios_sandbox","silent_microphone","silent_camera","leak_secret"}
class PolicyEngine:
    def classify_action(self, action: AgentAction) -> RiskClass:
        n=action.tool_name.lower(); d=action.description.lower()
        if n in BLOCKED_TOOLS or any(x in d for x in ["keylog","covert","bypass ios","silently record","reveal secret"]): return RiskClass.BLOCKED
        if n in DESTRUCTIVE_TOOLS or action.destructive: return RiskClass.HIGH
        if n in {"send_email","send_message"}: return RiskClass.HIGH
        if n in SENSITIVE_TOOLS or "cloud" in d: return RiskClass.HIGH
        if any(w in d for w in ["calendar","email","contact","personal","file"]): return RiskClass.MEDIUM
        return RiskClass.LOW
    def requires_approval(self, action: AgentAction, profile: UserProfile) -> bool:
        risk=self.classify_action(action)
        if profile.emergency_paused or profile.autonomy_mode in [AutonomyMode.OFF, AutonomyMode.SUGGEST_ONLY, AutonomyMode.DRAFT_ONLY]: return True
        if action.tool_name in {"send_email","send_message","cloud_model"}: return True
        if risk in [RiskClass.MEDIUM,RiskClass.HIGH,RiskClass.BLOCKED]: return True
        return profile.autonomy_mode != AutonomyMode.TRUSTED_WORKFLOW
    def can_execute(self, action: AgentAction, profile: UserProfile, approved: bool=False, double_confirmed: bool=False) -> tuple[bool,str]:
        risk=self.classify_action(action)
        if profile.emergency_paused: return False,"Emergency pause is enabled."
        if risk==RiskClass.BLOCKED: return False,"Action is blocked by hard safety policy."
        if action.destructive and not double_confirmed: return False,"Destructive action requires double confirmation."
        if self.requires_approval(action, profile) and not approved: return False,"Approval required before execution."
        return True,"Allowed."
    def cloud_allowed(self, grants:list[ConsentGrant], explicit_approval:bool, trusted_mode:bool=False) -> bool:
        return (explicit_approval or trusted_mode) and any(g.model_access_level!="local_only" and g.revoked_at is None for g in grants)
