from fastapi.testclient import TestClient
from shadow_node.main import app
c=TestClient(app)
print(c.get('/health').json())
consent=c.post('/consent',json={'data_source':'examples','scope':'selected_files','purpose':'demo','model_access_level':'local_only'}).json()
print('consent', consent['id'])
print(c.post('/memory/ingest_file',json={'path':'examples/sample_project_context.md','consent_grant_id':consent['id']}).json()['source']['title'])
print(c.post('/agent/ask',json={'prompt':'What is Project Alpha focused on?'}).json()['answer'])
print('approvals', len(c.get('/approvals').json()))
print('audit', len(c.get('/audit').json()))
