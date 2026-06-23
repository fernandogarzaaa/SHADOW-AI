from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class ConnectorCapability:
    name: str; consent_scope: str; oauth_scopes: list[str]
class Connector:
    name="base"
    capabilities: list[ConnectorCapability]=[]
    def ingest_preview(self) -> list[dict]: return []
class MockGmailConnector(Connector):
    name="gmail"; capabilities=[ConnectorCapability("read_selected_email","selected_items",["gmail.readonly"]), ConnectorCapability("draft_reply","draft_write_with_approval",["gmail.compose"])]
    def ingest_preview(self): return [{"title":"Mock Gmail","text":"Follow up with Project Alpha by Friday."}]
class MockCalendarConnector(Connector):
    name="calendar"; capabilities=[ConnectorCapability("read_events","read_only",["calendar.events.readonly"])]
    def ingest_preview(self): return [{"title":"Mock Calendar","text":"Project Alpha review at 10 AM Friday."}]
class MockFilesConnector(Connector):
    name="files"; capabilities=[ConnectorCapability("read_selected_files","selected_items",[])]
class MockNotesConnector(Connector):
    name="notes"; capabilities=[ConnectorCapability("manual_text","selected_items",[])]
class DesktopNodeTaskConnector(Connector):
    name="desktop_node"; capabilities=[ConnectorCapability("execute_safe_task","execute_with_approval",[])]
class ConnectorRegistry:
    def __init__(self): self._connectors={c.name:c for c in [MockGmailConnector(),MockCalendarConnector(),MockFilesConnector(),MockNotesConnector(),DesktopNodeTaskConnector()]}
    def list(self): return [{"name":n,"capabilities":[cap.__dict__ for cap in c.capabilities]} for n,c in sorted(self._connectors.items())]
    def get(self,name): return self._connectors[name]
