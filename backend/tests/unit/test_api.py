from fastapi.testclient import TestClient
from backend.app.main import app
def test_config_identity():
    data=TestClient(app).get('/api/config').json();assert data['candidate_id']=='mahendrushivam123@gmail.com';assert data['app_name']=='Alumnx AI Sales inbox task router'
def test_wrong_candidate_error_shape():
    r=TestClient(app).post('/ingest',json={'candidate_id':'wrong@example.com','emails':[{}]});assert r.status_code==400;assert r.json()['error']['code']=='candidate_id_mismatch'
