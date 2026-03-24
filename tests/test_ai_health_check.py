from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from app import app, LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY


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

    assert data['runtime_profile']['source'] == 'built_in_defaults'
    assert data['runtime_profile']['session_profile_active'] is False
    assert data['runtime_profile']['request_overrides_active'] is False
    assert data['runtime_profile']['merge_precedence'] == 'request_overrides_win_over_session_profile'

    assert by_backend['llama_cpp']['status'] == 'healthy'
    assert by_backend['llama_cpp']['readiness_code'] == 'ok'
    assert by_backend['llama_cpp']['models'] == ['llama-3.2']
    assert by_backend['llama_cpp']['effective_capability_overrides'] == {
        'supports_tools': True,
        'supports_json_mode': True,
        'supports_vision': False,
        'supports_streaming': True,
    }
    assert by_backend['llama_cpp']['runtime_profile']['source'] == 'built_in_defaults'

    assert by_backend['lm_studio']['status'] == 'timeout'
    assert by_backend['lm_studio']['readiness_code'] == 'backend_timeout'
    assert by_backend['lm_studio']['effective_capability_overrides'] == {
        'supports_tools': False,
        'supports_json_mode': True,
        'supports_vision': False,
        'supports_streaming': True,
    }
    assert by_backend['lm_studio']['runtime_profile']['source'] == 'built_in_defaults'


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

    assert data['runtime_profile']['source'] == 'built_in_defaults'

    assert by_backend['llama_cpp']['status'] == 'misconfigured'
    assert by_backend['llama_cpp']['readiness_code'] == 'backend_models_endpoint_not_found'
    assert by_backend['llama_cpp']['effective_capability_overrides'] == {
        'supports_tools': True,
        'supports_json_mode': True,
        'supports_vision': False,
        'supports_streaming': True,
    }
    assert by_backend['llama_cpp']['runtime_profile']['source'] == 'built_in_defaults'
    assert by_backend['lm_studio']['status'] == 'unreachable'
    assert by_backend['lm_studio']['readiness_code'] == 'backend_unreachable'
    assert by_backend['lm_studio']['effective_capability_overrides'] == {
        'supports_tools': False,
        'supports_json_mode': True,
        'supports_vision': False,
        'supports_streaming': True,
    }
    assert by_backend['lm_studio']['runtime_profile']['source'] == 'built_in_defaults'


def test_ai_backend_diagnostics_route_surfaces_runtime_capability_overrides(client):
    def fake_get(url, timeout=0):
        if url == 'http://lm.local/v1/models':
            return StubResponse(payload={'data': [{'id': 'qwen-local'}]}, ok=True, status_code=200)
        raise AssertionError(f"Unexpected URL: {url}")

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.LMStudioAdapterConfig.from_runtime_config', return_value=SimpleNamespace(base_url='http://lm.local', timeout_seconds=1.0)):

        response = client.post('/api/ai/backends/diagnostics', json={
            'backends': ['lm_studio'],
            'runtime_config': {
                'backends': {
                    'lm_studio': {
                        'supports_tools': True,
                        'supports_json_mode': False,
                        'capabilities': {
                            'supports_streaming': False,
                            'supports_vision': True,
                        },
                    },
                },
            },
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['runtime_profile']['source'] == 'request_overrides'
    assert data['runtime_profile']['request_overrides_active'] is True
    assert data['diagnostics'][0]['backend_id'] == 'lm_studio'
    assert data['diagnostics'][0]['effective_capability_overrides'] == {
        'supports_tools': True,
        'supports_json_mode': False,
        'supports_vision': True,
        'supports_streaming': False,
    }
    assert data['diagnostics'][0]['runtime_profile']['source'] == 'request_overrides'


def test_ai_backend_runtime_config_route_supports_get_set_and_clear(client):
    with client.session_transaction() as sess:
        sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
            'backends': {
                'llama_cpp': {'base_url': 'http://session-llama'}
            }
        }

    get_response = client.get('/api/ai/backends/runtime_config')
    assert get_response.status_code == 200
    assert get_response.get_json()['runtime_config'] == {
        'backends': {
            'llama_cpp': {'base_url': 'http://session-llama'}
        }
    }

    set_response = client.post('/api/ai/backends/runtime_config', json={
        'runtime_config': {
            'backends': {
                'llama_cpp': {'base_url': 'http://updated-llama', 'enabled': True},
                'lm_studio': {'base_url': 'http://updated-lm'},
            }
        }
    })
    assert set_response.status_code == 200
    assert set_response.get_json()['runtime_config']['backends']['llama_cpp']['base_url'] == 'http://updated-llama'

    clear_response = client.delete('/api/ai/backends/runtime_config')
    assert clear_response.status_code == 200
    assert clear_response.get_json()['runtime_config'] == {}


def test_ai_backend_diagnostics_route_merges_session_runtime_config_with_request_overrides(client):
    with client.session_transaction() as sess:
        sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
            'backends': {
                'llama_cpp': {
                    'base_url': 'http://session-llama',
                    'timeout_seconds': 1.0,
                }
            }
        }

    def fake_get(url, timeout=0):
        assert url == 'http://request-llama/v1/models'
        return StubResponse(payload={'data': [{'id': 'llama-from-request'}]}, ok=True, status_code=200)

    with patch('app.requests.get', side_effect=fake_get):
        response = client.post('/api/ai/backends/diagnostics', json={
            'backends': ['llama_cpp'],
            'runtime_config': {
                'backends': {
                    'llama_cpp': {
                        'base_url': 'http://request-llama',
                    }
                }
            },
        })

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['diagnostics'][0]['models'] == ['llama-from-request']
    assert data['runtime_profile']['source'] == 'session_profile_plus_request_overrides'
    assert data['runtime_profile']['session_profile_active'] is True
    assert data['runtime_profile']['request_overrides_active'] is True
    assert data['diagnostics'][0]['runtime_profile']['source'] == 'session_profile_plus_request_overrides'


def test_ai_health_check_uses_session_runtime_config_for_local_backends(client):
    with client.session_transaction() as sess:
        sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
            'backends': {
                'llama_cpp': {'base_url': 'http://session-llama', 'timeout_seconds': 1.0},
                'lm_studio': {'base_url': 'http://session-lm', 'timeout_seconds': 1.0},
            }
        }

    def fake_get(url, timeout=0):
        if url == 'http://localhost:11434/api/tags':
            return StubResponse(payload={'models': []})
        if url == 'http://session-llama/v1/models':
            return StubResponse(payload={'data': [{'id': 'llama-session-model'}]})
        if url == 'http://session-lm/v1/models':
            return StubResponse(payload={'data': [{'id': 'lm-session-model'}]})
        raise AssertionError(f"Unexpected URL: {url}")

    with patch('app.requests.get', side_effect=fake_get), \
         patch('app.get_gemini_client_for_session', return_value=None):
        response = client.get('/ai_health_check')

    assert response.status_code == 200
    data = response.get_json()
    assert data['models']['llama_cpp'] == ['llama-session-model']
    assert data['models']['lm_studio'] == ['lm-session-model']
    assert data['local_backend_diagnostics']['llama_cpp']['runtime_profile']['source'] == 'session_profile'
    assert data['local_backend_diagnostics']['lm_studio']['runtime_profile']['source'] == 'session_profile'
