from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from app import app


class StubResponse:
    def __init__(self, payload=None, ok=True, json_error=None):
        self._payload = payload
        self.ok = ok
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
         patch('app.LlamaCppAdapterConfig', return_value=SimpleNamespace(base_url='http://llama.local/')), \
         patch('app.LMStudioAdapterConfig', return_value=SimpleNamespace(base_url='http://lm.local')), \
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
         patch('app.LlamaCppAdapterConfig', return_value=SimpleNamespace(base_url='http://llama.local')), \
         patch('app.LMStudioAdapterConfig', return_value=SimpleNamespace(base_url='http://lm.local')), \
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
