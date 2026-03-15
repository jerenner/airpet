from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from app import app


class StubResponse:
    def __init__(self, payload=None, ok=True, status_code=200, json_error=None):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _gemini_model(name, supported_actions):
    return SimpleNamespace(name=name, supported_actions=supported_actions)


def test_ai_health_check_discovers_local_and_remote_models_with_normalized_lists(client):
    def fake_get(url, timeout=0):
        if url == 'http://localhost:11434/api/tags':
            return StubResponse(
                payload={
                    'models': [
                        {'name': 'qwen2.5:7b'},
                        {'name': 'qwen2.5:7b'},
                        {'name': '  llama3.2:3b  '},
                        {'name': ''},
                        {},
                    ]
                }
            )

        if url == 'http://llama.local/v1/models':
            return StubResponse(
                payload={
                    'data': [
                        {'id': 'Llama-3.2-3B-Instruct'},
                        {'id': 'Llama-3.2-3B-Instruct'},
                        {'id': '  qwen2.5-coder  '},
                        {'id': ''},
                        {'id': None},
                        'invalid-row',
                    ]
                }
            )

        if url == 'http://lm.local/v1/models':
            return StubResponse(payload={'data': [{'id': 'lmstudio-community/qwen2.5'}]})

        raise AssertionError(f"Unexpected URL: {url}")

    gemini_client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda: [
                _gemini_model('models/gemini-2.5-pro', ['generateContent']),
                _gemini_model('models/gemini-3-flash-preview', ['generateContent']),
                _gemini_model('models/gemini-2.5-flash', ['otherAction']),
                _gemini_model('models/not-allowed', ['generateContent']),
            ]
        )
    )

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.LlamaCppAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://llama.local/', timeout_seconds=1.0)), \
         patch('app.LMStudioAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://lm.local', timeout_seconds=1.0)), \
         patch('app.get_gemini_client_for_session', return_value=gemini_client):

        response = client.get('/ai_health_check')

    assert response.status_code == 200
    data = response.get_json()

    assert data['success'] is True
    assert data['models']['ollama'] == ['qwen2.5:7b', 'llama3.2:3b']
    assert data['models']['llama_cpp'] == ['Llama-3.2-3B-Instruct', 'qwen2.5-coder']
    assert data['models']['lm_studio'] == ['lmstudio-community/qwen2.5']
    assert data['models']['gemini'] == ['models/gemini-2.5-pro', 'models/gemini-3-flash-preview']


def test_ai_health_check_stays_successful_when_one_provider_returns_bad_payload(client):
    def fake_get(url, timeout=0):
        if url == 'http://localhost:11434/api/tags':
            return StubResponse(json_error=ValueError('invalid ollama payload'))

        if url == 'http://llama.local/v1/models':
            raise requests.exceptions.RequestException('llama.cpp offline')

        if url == 'http://lm.local/v1/models':
            return StubResponse(payload={'data': [{'id': 'lmstudio-community/gemma-3-12b'}]})

        raise AssertionError(f"Unexpected URL: {url}")

    gemini_client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda: [
                _gemini_model('models/gemini-2.5-flash', ['generateContent']),
            ]
        )
    )

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.LlamaCppAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://llama.local', timeout_seconds=1.0)), \
         patch('app.LMStudioAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://lm.local', timeout_seconds=1.0)), \
         patch('app.get_gemini_client_for_session', return_value=gemini_client):

        response = client.get('/ai_health_check')

    assert response.status_code == 200
    data = response.get_json()

    assert data['success'] is True
    assert data['models']['ollama'] == []
    assert data['models']['llama_cpp'] == []
    assert data['models']['lm_studio'] == ['lmstudio-community/gemma-3-12b']
    assert data['models']['gemini'] == ['models/gemini-2.5-flash']
    assert data['error_ollama'] == 'invalid ollama payload'


def test_ai_backend_diagnostics_route_reports_healthy_and_timeout_statuses(client):
    def fake_get(url, timeout=0):
        if url == 'http://llama.local/v1/models':
            return StubResponse(payload={'data': [{'id': 'llama-3.2'}]}, ok=True, status_code=200)
        if url == 'http://lm.local/v1/models':
            raise requests.exceptions.ConnectTimeout('timed out')
        raise AssertionError(f"Unexpected URL: {url}")

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.LlamaCppAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://llama.local', timeout_seconds=1.0)), \
         patch('app.LMStudioAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://lm.local', timeout_seconds=1.0)):

        response = client.get('/api/ai/backends/diagnostics')

    assert response.status_code == 200
    data = response.get_json()

    assert data['success'] is True
    by_backend = {item['backend_id']: item for item in data['diagnostics']}

    assert by_backend['llama_cpp']['status'] == 'healthy'
    assert by_backend['llama_cpp']['readiness_code'] == 'ok'
    assert by_backend['llama_cpp']['models'] == ['llama-3.2']

    assert by_backend['lm_studio']['status'] == 'timeout'
    assert by_backend['lm_studio']['readiness_code'] == 'backend_timeout'


def test_ai_backend_diagnostics_route_classifies_unreachable_and_misconfigured(client):
    def fake_get(url, timeout=0):
        if url == 'http://llama.local/v1/models':
            return StubResponse(payload={'error': 'not found'}, ok=False, status_code=404)
        if url == 'http://lm.local/v1/models':
            raise requests.exceptions.ConnectionError('connection refused')
        raise AssertionError(f"Unexpected URL: {url}")

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.LlamaCppAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://llama.local', timeout_seconds=1.0)), \
         patch('app.LMStudioAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://lm.local', timeout_seconds=1.0)):

        response = client.post('/api/ai/backends/diagnostics', json={'backends': ['llama_cpp', 'lm_studio']})

    assert response.status_code == 200
    data = response.get_json()

    assert data['success'] is True
    by_backend = {item['backend_id']: item for item in data['diagnostics']}

    assert by_backend['llama_cpp']['status'] == 'misconfigured'
    assert by_backend['llama_cpp']['readiness_code'] == 'backend_models_endpoint_not_found'
    assert by_backend['lm_studio']['status'] == 'unreachable'
    assert by_backend['lm_studio']['readiness_code'] == 'backend_unreachable'
