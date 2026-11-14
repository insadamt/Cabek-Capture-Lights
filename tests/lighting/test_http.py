"""Verify the standalone API, token-free lifecycle delivery and deadline replay.

Depends on TestClient and memory-only output; no CABEK application is imported.
"""
from fastapi.testclient import TestClient
from lighting_api.main import create_app
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_service import LightingService


def make_client():
    now=[0.0]
    config=LightingSettings(enabled=True, driver='simulated_pixels',)
    service=LightingService(config,clock=lambda:now[0])
    return TestClient(create_app(service=service)),service,now

def test_standalone_api_events_and_scan_priority():
    client,service,now=make_client()
    assert client.get('/api/v1/lights/status').status_code==200
    event=dict(session_id='application',sequence=1,state='READY',ready=True)
    assert client.post('/api/v1/lights/events',json=event).status_code==202
    assert len(client.get('/api/v1/lights/effects').json())==16
    assert client.post('/api/v1/lights/effects',json={'effect':'breathing','repeat':True}).status_code==202
    event.update(sequence=2,state='SCANNING',capture_id='scan')
    result=client.post('/api/v1/lights/events',json=event)
    assert result.status_code==202 and not result.json()['preview_active']
    assert client.post('/api/v1/lights/stop').status_code==409
    event.update(sequence=3,state='COMPLETED',capture_id=None,elapsed_ms=4000)
    assert client.post('/api/v1/lights/events',json=event).status_code==202
    deadline=service.state.completion_deadline
    now[0]=1
    client.post('/api/v1/lights/events',json=event)
    assert service.state.completion_deadline==deadline
    now[0]=6
    assert client.get('/api/v1/lights/status').json()['state']=='READY'
    event.update(sequence=4,state='SCANNING',capture_id=None)
    assert client.post('/api/v1/lights/events',json=event).status_code==422


def test_openapi_has_no_auth_and_disabled_service_still_returns_503():
    client, _, _ = make_client()
    spec = client.get('/openapi.json').json()
    assert not spec.get('components', {}).get('securitySchemes')
    for path in spec['paths'].values():
        assert all(not operation.get('security') for operation in path.values())
    disabled = TestClient(create_app(settings=LightingSettings()))
    assert disabled.get('/api/v1/lights/status').status_code == 503


def test_previews_tests_and_stop_work_without_headers():
    client, _, _ = make_client()
    event = dict(session_id='app', sequence=1, state='READY', ready=True)
    assert client.post('/api/v1/lights/events', json=event).status_code == 202
    assert client.post('/api/v1/lights/test', json={'color':'RED'}).status_code == 202
    assert client.post('/api/v1/lights/effects', json={'effect':'solid'}).status_code == 202
    assert client.post('/api/v1/lights/stop').status_code == 202
    assert client.post('/api/v1/lights/state', json={'state':'OFF'}).status_code == 202
