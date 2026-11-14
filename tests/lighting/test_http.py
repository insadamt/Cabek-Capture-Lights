"""Verify the two-route contract with real worker scheduling and mock serial.

Depends on TestClient and in-memory firmware; CABEK AI and USB are absent.
"""
import pytest
from fastapi.testclient import TestClient

from firmware_fake import FirmwareSerial
from lighting_api.lighting_config import LightingSettings
from lighting_api.lighting_effects import GLOBAL_EFFECTS
from lighting_api.lighting_protocol import SerialLightingLink
from lighting_api.lighting_service import LightingService
from lighting_api.main import create_app


@pytest.fixture
def controller():
    settings = LightingSettings(port='fake', timeout=.01)
    port = FirmwareSerial()
    service = LightingService(settings, SerialLightingLink(settings, lambda **kwargs: port))
    with TestClient(create_app(service=service)) as client:
        yield client, service, port
    assert not service.thread.is_alive() and service.link.port is None


def test_exactly_two_endpoints_and_defaults_work_without_application(controller):
    client, service, port = controller
    assert set(client.app.openapi()['paths']) == {'/api/lights/set', '/api/lights/off'}
    response = client.post('/api/lights/set', json={})
    assert response.status_code == 200
    assert response.json() == {'success': True, 'effect': 'solid', 'status': 'active'}
    assert port.output == (255, 255, 255)
    assert client.post('/api/lights/off').json() == {'success': True, 'status': 'off'}
    assert service.active is None and port.output == (0, 0, 0)
    assert client.post('/api/v1/lights/events', json={}).status_code == 404


@pytest.mark.parametrize('effect', GLOBAL_EFFECTS)
def test_every_effect_is_accepted_and_replaced(controller, effect):
    client, service, port = controller
    payload = {'effect': effect}
    if effect == 'color_cycle':
        payload['colors'] = ['#0066FF', '#8B00FF', '#00FFFF']
    response = client.post('/api/lights/set', json=payload)
    assert response.status_code == (200 if effect == 'solid' else 202)
    assert response.json()['effect'] == effect
    assert client.post('/api/lights/set', json={'color': '#FF0000'}).status_code == 200
    assert port.output == (255, 0, 0)


def test_validation_and_brightness(controller):
    client, _, port = controller
    assert client.post('/api/lights/set', json={'brightness': 101}).status_code == 422
    assert client.post('/api/lights/set', json={'effect': 'missing'}).json()['success'] is False
    response = client.post('/api/lights/set', json={'color': '#FF8000', 'brightness': 50, 'speed': 'ignored'})
    assert response.status_code == 200 and port.output == (128, 64, 0)


def test_disconnected_hardware_is_not_successful_and_off_cancels(controller):
    client, service, port = controller
    client.post('/api/lights/set', json={'effect': 'breathing', 'repeat': True})
    port.broken = True
    response = client.post('/api/lights/off')
    assert response.status_code == 503 and response.json()['success'] is False
    assert service.active is None and service.desired_output == (0, 0, 0)
    response = client.post('/api/lights/set', json={'color': '#FF0000'})
    assert response.status_code == 503


def test_legacy_animations_fail_clearly_but_basic_colors_still_work(controller):
    client, _, port = controller
    port.rgb_supported = False
    assert client.post('/api/lights/set', json={'color': '#0000FF'}).status_code == 200
    response = client.post('/api/lights/set', json={'effect': 'breathing'})
    assert response.status_code == 501
    assert response.json()['error']['code'] == 'unsupported_firmware'
    assert client.post('/api/lights/set', json={'color': '#123456'}).status_code == 501
    assert client.post('/api/lights/off').status_code == 200
