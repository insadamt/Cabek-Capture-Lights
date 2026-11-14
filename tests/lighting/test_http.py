"""Verify the standalone API, authenticated lifecycle delivery and deadline replay.

Depends on TestClient and memory-only output; no CABEK application is imported.
"""
from fastapi.testclient import TestClient
from lighting_api.main import create_app
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_service import LightingService

CONTROL={'Authorization':'Bearer '+'c'*32}
MAINTENANCE={'Authorization':'Bearer '+'m'*32}

def make_client():
    now=[0.0]
    config=LightingSettings(enabled=True, driver='simulated_pixels',token='c'*32,maintenance_token='m'*32)
    service=LightingService(config,clock=lambda:now[0])
    return TestClient(create_app(service=service)),service,now

def test_standalone_api_events_and_scan_priority():
    client,service,now=make_client()
    assert client.get('/api/v1/lights/status').status_code==401
    event=dict(session_id='application',sequence=1,state='READY',ready=True)
    assert client.post('/api/v1/lights/events',headers=CONTROL,json=event).status_code==202
    assert len(client.get('/api/v1/lights/effects',headers=CONTROL).json())==16
    assert client.post('/api/v1/lights/effects',headers=MAINTENANCE,json={'effect':'breathing','repeat':True}).status_code==202
    event.update(sequence=2,state='SCANNING',capture_id='scan')
    result=client.post('/api/v1/lights/events',headers=CONTROL,json=event)
    assert result.status_code==202 and not result.json()['preview_active']
    assert client.post('/api/v1/lights/stop',headers=MAINTENANCE).status_code==409
    event.update(sequence=3,state='COMPLETED',capture_id=None,elapsed_ms=4000)
    assert client.post('/api/v1/lights/events',headers=CONTROL,json=event).status_code==202
    deadline=service.state.completion_deadline
    now[0]=1
    client.post('/api/v1/lights/events',headers=CONTROL,json=event)
    assert service.state.completion_deadline==deadline
    now[0]=6
    assert client.get('/api/v1/lights/status',headers=CONTROL).json()['state']=='READY'
    event.update(sequence=4,state='SCANNING',capture_id=None)
    assert client.post('/api/v1/lights/events',headers=CONTROL,json=event).status_code==422
