import pytest
import json
from unittest.mock import MagicMock, patch
from app import app, dispatch_ai_tool, LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator
from src.ai_tools import AI_GEOMETRY_TOOLS

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_ai_geometry_tools_schema_is_valid_for_gemini_generate_content_config():
    types = pytest.importorskip("google.genai.types")

    cfg = types.GenerateContentConfig(
        tools=[{"function_declarations": AI_GEOMETRY_TOOLS}]
    )

    assert cfg is not None


def test_ai_chat_flow_mocked(client):
    """Verify that the AI can trigger a simulation via chat using test_client."""
    from google.genai import types
    
    # turn 1: model calls tool
    mock_call_part = MagicMock()
    mock_call_part.function_call = MagicMock()
    mock_call_part.function_call.name = "run_simulation"
    mock_call_part.function_call.args = {"events": 10}
    mock_call_part.text = None

    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content.parts = [mock_call_part]
    mock_response.candidates[0].content.role = "model"
    
    # turn 2: model gives final text
    final_part = MagicMock()
    final_part.function_call = None
    final_part.text = "Simulation started."
    
    final_response = MagicMock()
    final_response.candidates = [MagicMock()]
    final_response.candidates[0].content.parts = [final_part]
    final_response.candidates[0].content.role = "model"
    final_response.text = "Simulation started."

    with patch('app.get_gemini_client_for_session') as MockClientGetter, \
         patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.types.GenerateContentConfig', side_effect=lambda **kwargs: kwargs):
        
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm
        
        mock_client = MagicMock()
        MockClientGetter.return_value = mock_client
        # The loop iterates up to 5 times.
        mock_client.models.generate_content.side_effect = [mock_response, final_response]
        
        with patch('threading.Thread') as MockThread, \
             patch('app.run_g4_simulation') as MockRunG4:
            
            payload = {"message": "Run a quick sim", "model": "models/gemini-2.0-flash-exp"}
            response = client.post("/api/ai/chat", json=payload)
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['success']
            # We expect job_id to be injected into the response
            assert 'job_id' in data, f"Data was: {data}"
            assert "Simulation started." in data['message']
            assert MockThread.called

def test_ai_chat_handles_empty_gemini_candidate_content_with_text_fallback(client):
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content = None
    mock_response.text = "Fallback response from Gemini."

    with patch('app.get_gemini_client_for_session') as MockClientGetter, \
         patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.types.GenerateContentConfig', side_effect=lambda **kwargs: kwargs):

        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        mock_client = MagicMock()
        MockClientGetter.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_response

        payload = {"message": "hello", "model": "models/gemini-2.0-flash-exp"}
        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert "Fallback response from Gemini." in data['message']


def test_ai_chat_backend_selector_uses_llama_cpp_for_tool_requests_when_enabled(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:

        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='llama-local',
            text='Selection handled locally.',
            usage={'prompt_tokens': 42, 'completion_tokens': 7},
            raw_response={},
        )

        payload = {
            "message": "hello",
            "model": "models/gemini-2.0-flash-exp",
            "backend_selector": {
                "preferred_backend_id": "llama_cpp",
                "allow_fallback": True,
                "runtime_config": {
                    "backends": {
                        "llama_cpp": {"enabled": True}
                    }
                },
                "requirements": {
                    "require_tools": True,
                    "require_json_mode": True
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["backend_selection"]["resolved_backend_id"] == "llama_cpp"
        assert data["backend_selection"]["used_fallback"] is False
        assert data["backend_selection"]["tried"][0]["backend_id"] == "llama_cpp"
        assert data["backend_selection"]["tried"][0]["missing_capabilities"] == []


def test_ai_chat_backend_selector_returns_deterministic_no_fallback_error_for_lm_studio_tools(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'lm_studio',
             'status': 'healthy',
             'readiness_code': 'ok',
             'ready': True,
         }):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        payload = {
            "message": "hello",
            "model": "models/gemini-2.0-flash-exp",
            "backend_selector": {
                "preferred_backend_id": "lm_studio",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "llama_cpp": {"enabled": True},
                        "lm_studio": {"enabled": True}
                    }
                },
                "requirements": {
                    "require_tools": True,
                    "require_json_mode": True,
                    "require_streaming": True,
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "AI backend selection failed" in data["error"]
        assert data["backend_selection"]["preferred_backend_id"] == "lm_studio"
        assert data["backend_selection"]["allow_fallback"] is False
        assert "'backend_id': 'lm_studio'" in data["backend_selection"]["selection_error"]
        assert "'missing_capabilities': ['tools']" in data["backend_selection"]["selection_error"]
        assert data["backend_diagnostics"]["failure_stage"] == "selector_requirements"
        assert data["backend_diagnostics"]["error_code"] == "backend_selection_failed"
        assert data["backend_diagnostics"]["readiness"]["status"] == "healthy"
        assert data["backend_diagnostics"]["effective_capability_overrides"] == {
            "supports_tools": False,
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_streaming": True,
        }
        assert data["backend_diagnostics"]["readiness"]["effective_capability_overrides"] == {
            "supports_tools": False,
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_streaming": True,
        }
        assert data["backend_diagnostics"]["selector_requirements"] == {
            "require_tools": True,
            "require_json_mode": True,
            "require_vision": False,
            "require_streaming": True,
            "min_context_tokens": None,
        }
        assert data["backend_diagnostics"]["contradictions"] == [
            {
                "code": "selector_requirement_capability_mismatch",
                "contradiction_class": "selector_contract_mismatch",
                "summary": "Selector-required capabilities are disabled in effective backend capability overrides.",
                "details": {
                    "required_capability_flags": [
                        "supports_tools",
                        "supports_json_mode",
                        "supports_streaming",
                    ],
                    "unsatisfied_capability_flags": ["supports_tools"],
                    "effective_capability_overrides": {
                        "supports_tools": False,
                        "supports_json_mode": True,
                        "supports_vision": False,
                        "supports_streaming": True,
                    },
                },
            },
        ]
        assert data["backend_diagnostics"]["remediation"]["summary"] == "Selector requirements conflict with effective backend capability overrides."
        assert data["backend_diagnostics"]["remediation"]["primary_contradiction_class"] == "selector_contract_mismatch"
        assert data["backend_diagnostics"]["remediation"]["contradiction_classes"] == [
            "selector_contract_mismatch",
        ]
        assert data["backend_diagnostics"]["remediation"]["contradiction_codes"] == [
            "selector_requirement_capability_mismatch",
        ]
        assert data["backend_diagnostics"]["remediation"]["action_codes"] == [
            "align_selector_requirements_with_effective_capabilities",
            "update_runtime_capability_overrides_for_selected_backend",
            "allow_fallback_or_choose_capability_compatible_backend",
        ]


def test_ai_chat_backend_selector_requirement_failure_without_capability_contradiction_keeps_requirement_remediation(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'lm_studio',
             'status': 'healthy',
             'readiness_code': 'ok',
             'ready': True,
         }):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        payload = {
            "message": "hello",
            "backend_selector": {
                "preferred_backend_id": "lm_studio",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "lm_studio": {
                            "enabled": True,
                            "max_context_tokens": 1024,
                            "supports_tools": True,
                            "supports_json_mode": True,
                            "supports_streaming": True,
                        }
                    }
                },
                "requirements": {
                    "require_tools": False,
                    "require_json_mode": False,
                    "require_streaming": False,
                    "min_context_tokens": 4096,
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert data["backend_diagnostics"]["failure_stage"] == "selector_requirements"
        assert data["backend_diagnostics"]["selector_requirements"] == {
            "require_tools": False,
            "require_json_mode": False,
            "require_vision": False,
            "require_streaming": False,
            "min_context_tokens": 4096,
        }
        assert data["backend_diagnostics"]["contradictions"] == []
        assert data["backend_diagnostics"]["remediation"]["summary"] == "Selected backend cannot satisfy the requested capabilities."
        assert data["backend_diagnostics"]["remediation"]["primary_contradiction_class"] is None
        assert data["backend_diagnostics"]["remediation"]["contradiction_classes"] == []
        assert data["backend_diagnostics"]["remediation"]["contradiction_codes"] == []
        assert data["backend_diagnostics"]["remediation"]["action_codes"] == [
            "review_backend_requirements",
            "allow_backend_fallback",
            "switch_backend_for_missing_capabilities",
        ]


def test_ai_chat_backend_selector_invokes_local_text_adapter_when_selected(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='llama-3.2-local',
            text='{"status":"ok"}',
            usage={'prompt_tokens': 42, 'completion_tokens': 9},
        )

        payload = {
            "message": "Summarize the detector setup in compact JSON.",
            "model": "models/gemini-2.0-flash-exp",
            "backend_selector": {
                "preferred_backend_id": "llama_cpp",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "llama_cpp": {
                            "enabled": True,
                            "model": "llama-3.2-local"
                        }
                    }
                },
                "requirements": {
                    "require_tools": False,
                    "require_json_mode": True,
                    "require_streaming": False
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == '{"status":"ok"}'
        assert data["backend_selection"]["resolved_backend_id"] == "llama_cpp"
        assert data["backend_selection"]["execution_mode"] == "local_text_adapter"
        assert data["backend_selection"]["resolved_model"] == "llama-3.2-local"
        assert data["backend_execution"]["backend_id"] == "llama_cpp"
        assert data["backend_execution"]["usage"] == {'prompt_tokens': 42, 'completion_tokens': 9}
        MockInvokeAdapter.assert_called_once()


def test_ai_chat_local_llama_executes_tool_calls_from_json_fallback(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter, \
         patch('app.dispatch_ai_tool') as MockDispatchTool:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.side_effect = [
            MagicMock(
                backend_id='llama_cpp',
                model='qwen-local',
                text=(
                    "I'll define spacing and proceed.\n\n"
                    "```json\n"
                    "{\n"
                    "  \"tool_calls\": [\n"
                    "    {\"tool\": \"manage_define\", \"name\": \"SiPM_spacing\", \"value\": \"10\"}\n"
                    "  ]\n"
                    "}\n"
                    "```"
                ),
                usage={'prompt_tokens': 50, 'completion_tokens': 20},
                raw_response={},
            ),
            MagicMock(
                backend_id='llama_cpp',
                model='qwen-local',
                text='Done. Created the SiPM grid on kapton.',
                usage={'prompt_tokens': 58, 'completion_tokens': 18},
                raw_response={},
            ),
        ]

        MockDispatchTool.return_value = {"success": True}

        payload = {
            "message": "Create an 8x8 SiPM matrix.",
            "model": "llama_cpp::qwen-local",
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Done. Created the SiPM grid on kapton." in data["message"]
        assert MockInvokeAdapter.call_count == 2
        MockDispatchTool.assert_called_once()
        called_tool_name = MockDispatchTool.call_args.args[1]
        called_tool_args = MockDispatchTool.call_args.args[2]
        assert called_tool_name == "manage_define"
        assert called_tool_args == {"name": "SiPM_spacing", "value": "10"}

        second_turn_request = MockInvokeAdapter.call_args_list[1].args[1]
        assert any(msg.role == "assistant" and msg.tool_calls for msg in second_turn_request.messages)
        assert any(msg.role == "tool" and msg.tool_call_id for msg in second_turn_request.messages)


def test_ai_chat_local_lm_studio_executes_tool_calls_when_tools_capability_override_is_enabled(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter, \
         patch('app.dispatch_ai_tool') as MockDispatchTool:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.side_effect = [
            MagicMock(
                backend_id='lm_studio',
                model='qwen2.5-local',
                text=(
                    "Executing the requested update.\n\n"
                    "```json\n"
                    "{\n"
                    "  \"tool_calls\": [\n"
                    "    {\"tool\": \"manage_define\", \"name\": \"pitch_mm\", \"value\": \"3.5\"}\n"
                    "  ]\n"
                    "}\n"
                    "```"
                ),
                usage={'prompt_tokens': 42, 'completion_tokens': 14},
                raw_response={},
            ),
            MagicMock(
                backend_id='lm_studio',
                model='qwen2.5-local',
                text='Done. Applied pitch define update.',
                usage={'prompt_tokens': 49, 'completion_tokens': 11},
                raw_response={},
            ),
        ]

        MockDispatchTool.return_value = {"success": True}

        payload = {
            "message": "Set pitch define to 3.5 mm.",
            "backend_selector": {
                "preferred_backend_id": "lm_studio",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "lm_studio": {
                            "enabled": True,
                            "model": "qwen2.5-local",
                            "supports_tools": True,
                        }
                    }
                },
                "requirements": {
                    "require_tools": True,
                    "require_json_mode": True,
                    "require_streaming": False,
                },
            },
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Done. Applied pitch define update." in data["message"]
        assert data["backend_selection"]["resolved_backend_id"] == "lm_studio"
        assert data["backend_selection"]["execution_mode"] == "local_text_adapter"
        assert MockInvokeAdapter.call_count == 2
        MockDispatchTool.assert_called_once()

        called_tool_name = MockDispatchTool.call_args.args[1]
        called_tool_args = MockDispatchTool.call_args.args[2]
        assert called_tool_name == "manage_define"
        assert called_tool_args == {"name": "pitch_mm", "value": "3.5"}

        second_turn_request = MockInvokeAdapter.call_args_list[1].args[1]
        assert any(msg.role == "assistant" and msg.tool_calls for msg in second_turn_request.messages)
        assert any(msg.role == "tool" and msg.tool_call_id for msg in second_turn_request.messages)


def test_ai_chat_backend_selector_returns_deterministic_local_invocation_error_payload(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend', side_effect=RuntimeError('connection refused')), \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'lm_studio',
             'status': 'unreachable',
             'readiness_code': 'backend_unreachable',
             'ready': False,
         }):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        payload = {
            "message": "Summarize in JSON.",
            "model": "models/gemini-2.0-flash-exp",
            "backend_selector": {
                "preferred_backend_id": "lm_studio",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "lm_studio": {
                            "enabled": True,
                            "base_url": "http://localhost:1234",
                            "supports_tools": True,
                            "supports_json_mode": True,
                            "capabilities": {
                                "supports_vision": True,
                                "supports_streaming": False,
                            },
                        }
                    }
                },
                "requirements": {
                    "require_tools": False,
                    "require_json_mode": True,
                    "require_streaming": False
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 502
        data = response.get_json()
        assert data["success"] is False
        assert "AI backend invocation failed (lm_studio)" in data["error"]
        assert data["backend_selection"]["resolved_backend_id"] == "lm_studio"
        assert data["backend_selection"]["execution_mode"] == "local_text_adapter"
        assert data["backend_diagnostics"]["failure_stage"] == "backend_runtime"
        assert data["backend_diagnostics"]["error_code"] == "local_backend_invocation_failed"
        assert data["backend_diagnostics"]["readiness"]["status"] == "unreachable"
        assert data["backend_diagnostics"]["effective_capability_overrides"] == {
            "supports_tools": True,
            "supports_json_mode": True,
            "supports_vision": True,
            "supports_streaming": False,
        }
        assert data["backend_diagnostics"]["readiness"]["effective_capability_overrides"] == {
            "supports_tools": True,
            "supports_json_mode": True,
            "supports_vision": True,
            "supports_streaming": False,
        }
        assert data["backend_diagnostics"]["selector_requirements"] == {
            "require_tools": False,
            "require_json_mode": True,
            "require_vision": False,
            "require_streaming": False,
            "min_context_tokens": None,
        }
        assert data["backend_diagnostics"]["contradictions"] == []
        assert data["backend_diagnostics"]["remediation"]["summary"] == "LM Studio is unreachable from AIRPET."
        assert data["backend_diagnostics"]["remediation"]["primary_contradiction_class"] is None
        assert data["backend_diagnostics"]["remediation"]["action_codes"] == [
            "start_local_backend_service",
            "verify_backend_base_url_and_port",
            "verify_models_endpoint_reachable",
        ]


def test_ai_chat_backend_selector_surfaces_runtime_backend_mismatch_when_readiness_is_healthy(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend', side_effect=RuntimeError('tool call parse failure')), \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'lm_studio',
             'status': 'healthy',
             'readiness_code': 'ok',
             'ready': True,
         }):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        payload = {
            "message": "Apply local tool flow.",
            "backend_selector": {
                "preferred_backend_id": "lm_studio",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "lm_studio": {
                            "enabled": True,
                            "supports_tools": True,
                            "supports_json_mode": True,
                        }
                    }
                },
                "requirements": {
                    "require_tools": True,
                    "require_json_mode": True,
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 502
        data = response.get_json()
        assert data["success"] is False
        assert data["backend_diagnostics"]["failure_stage"] == "backend_runtime"
        assert data["backend_diagnostics"]["readiness"]["status"] == "healthy"
        assert data["backend_diagnostics"]["contradictions"] == [
            {
                "code": "runtime_failure_despite_healthy_readiness",
                "contradiction_class": "runtime_backend_mismatch",
                "summary": "Runtime invocation failed even though backend readiness probe reported healthy status.",
                "details": {
                    "readiness_status": "healthy",
                    "readiness_code": "ok",
                },
            },
        ]
        assert data["backend_diagnostics"]["remediation"]["summary"] == "LM Studio failed at runtime despite a healthy readiness probe."
        assert data["backend_diagnostics"]["remediation"]["primary_contradiction_class"] == "runtime_backend_mismatch"
        assert data["backend_diagnostics"]["remediation"]["contradiction_classes"] == [
            "runtime_backend_mismatch",
        ]
        assert data["backend_diagnostics"]["remediation"]["contradiction_codes"] == [
            "runtime_failure_despite_healthy_readiness",
        ]
        assert data["backend_diagnostics"]["remediation"]["action_codes"] == [
            "capture_runtime_backend_request_context",
            "inspect_backend_runtime_logs",
            "reprobe_backend_after_runtime_failure",
        ]


def test_ai_chat_infers_local_backend_selector_from_model_prefix(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='llama-3.2-local',
            text='{"status":"ok"}',
            usage={'prompt_tokens': 11, 'completion_tokens': 5},
        )

        payload = {
            "message": "Return JSON only.",
            "model": "llama_cpp::llama-3.2-local",
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["backend_selection"]["resolved_backend_id"] == "llama_cpp"
        assert data["backend_selection"]["execution_mode"] == "local_text_adapter"
        assert data["backend_selection"]["selector_source"] == "model_prefix"

        MockInvokeAdapter.assert_called_once()
        invocation_request = MockInvokeAdapter.call_args.args[1]
        assert invocation_request.require_tools is True
        assert invocation_request.require_json_mode is True
        assert invocation_request.require_streaming is False


def test_ai_chat_model_prefix_uses_session_runtime_config_defaults(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        with client.session_transaction() as sess:
            sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
                'backends': {
                    'llama_cpp': {
                        'base_url': 'http://session-llama',
                        'timeout_seconds': 33,
                        'enabled': False,
                        'headers': {'Authorization': 'Bearer session-token'},
                    }
                }
            }

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='qwen-local',
            text='{"ok":true}',
            usage={'prompt_tokens': 3, 'completion_tokens': 2},
            raw_response={},
        )

        response = client.post('/api/ai/chat', json={
            'message': 'Return compact JSON.',
            'model': 'llama_cpp::qwen-local',
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['backend_selection']['selector_source'] == 'model_prefix'

        runtime_config = MockInvokeAdapter.call_args.kwargs['runtime_config']
        llama_cfg = runtime_config['backends']['llama_cpp']
        assert llama_cfg['base_url'] == 'http://session-llama'
        assert llama_cfg['timeout_seconds'] == 33
        assert llama_cfg['headers'] == {'Authorization': 'Bearer session-token'}
        assert llama_cfg['enabled'] is True
        assert llama_cfg['model'] == 'qwen-local'


def _parse_sse_data_events(response):
    events = []
    for line in response.get_data(as_text=True).splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


def test_ai_chat_stream_persists_final_reply_in_history_for_local_adapter(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='qwen-local',
            text='All set.',
            usage={'prompt_tokens': 7, 'completion_tokens': 3},
            raw_response={},
        )

        response = client.post('/api/ai/chat/stream', json={
            'message': 'Say hello.',
            'model': 'llama_cpp::qwen-local',
        })

        assert response.status_code == 200
        events = _parse_sse_data_events(response)
        complete_events = [evt for evt in events if evt.get('type') == 'complete']
        assert complete_events, events
        assert complete_events[-1]['message'] == 'All set.'

        history_response = client.get('/api/ai/history')
        assert history_response.status_code == 200
        history = history_response.get_json()['history']

        final_messages = [
            msg for msg in history
            if msg.get('role') == 'assistant'
            and msg.get('content') == 'All set.'
            and not (msg.get('metadata') or {}).get('_intermediate')
        ]
        assert final_messages, history


def test_ai_chat_stream_persists_final_reply_in_history_for_gemini(client):
    final_part = MagicMock()
    final_part.function_call = None
    final_part.text = "Gemini final reply."

    final_response = MagicMock()
    final_response.candidates = [MagicMock()]
    final_response.candidates[0].content.parts = [final_part]
    final_response.candidates[0].content.role = "model"
    final_response.text = "Gemini final reply."

    with patch('app.get_gemini_client_for_session') as MockClientGetter, \
         patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.types.GenerateContentConfig', side_effect=lambda **kwargs: kwargs):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = final_response
        MockClientGetter.return_value = mock_client

        response = client.post('/api/ai/chat/stream', json={
            'message': 'Say hello.',
            'model': 'models/gemini-2.0-flash-exp',
        })

        assert response.status_code == 200
        events = _parse_sse_data_events(response)
        complete_events = [evt for evt in events if evt.get('type') == 'complete']
        assert complete_events, events
        assert complete_events[-1]['message'] == 'Gemini final reply.'

        history_response = client.get('/api/ai/history')
        assert history_response.status_code == 200
        history = history_response.get_json()['history']

        final_messages = [
            msg for msg in history
            if msg.get('role') == 'model'
            and (msg.get('parts') or [{}])[0].get('text') == 'Gemini final reply.'
            and not (msg.get('metadata') or {}).get('_intermediate')
        ]
        assert final_messages, history


def test_ai_chat_stream_gemini_handles_mixed_history_message_formats(client):
    final_part = MagicMock()
    final_part.function_call = None
    final_part.text = "Gemini reply after mixed history."

    final_response = MagicMock()
    final_response.candidates = [MagicMock()]
    final_response.candidates[0].content.parts = [final_part]
    final_response.candidates[0].content.role = "model"
    final_response.text = "Gemini reply after mixed history."

    with patch('app.get_gemini_client_for_session') as MockClientGetter, \
         patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.types.GenerateContentConfig', side_effect=lambda **kwargs: kwargs):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        pm.chat_history = [
            {
                "role": "assistant",
                "content": "Earlier local assistant reply.",
                "tool_calls": [
                    {
                        "id": "hist_call_1",
                        "type": "function",
                        "function": {"name": "manage_define", "arguments": "{\"name\":\"si_thickness\",\"value\":\"0.1\"}"},
                    }
                ],
            },
            {
                "role": "tool",
                "name": "manage_define",
                "content": json.dumps({"success": True, "message": "Define updated."}),
                "tool_call_id": "hist_call_1",
            },
        ]
        MockPMGetter.return_value = pm

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = final_response
        MockClientGetter.return_value = mock_client

        response = client.post('/api/ai/chat/stream', json={
            'message': 'Continue from here.',
            'model': 'models/gemini-2.0-flash-exp',
        })

        assert response.status_code == 200
        events = _parse_sse_data_events(response)
        complete_events = [evt for evt in events if evt.get('type') == 'complete']
        assert complete_events, events
        assert complete_events[-1]['message'] == 'Gemini reply after mixed history.'


@pytest.mark.parametrize(
    "route_path",
    [
        "/api/ai/chat",
        "/api/ai/chat/stream",
    ],
)
def test_local_selector_runtime_profile_merge_is_identical_for_chat_and_stream_routes(client, route_path):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend') as MockInvokeAdapter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        with client.session_transaction() as sess:
            sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
                'backends': {
                    'llama_cpp': {
                        'base_url': 'http://session-llama',
                        'timeout_seconds': 33,
                        'enabled': False,
                        'headers': {'Authorization': 'Bearer session-token'},
                    }
                }
            }

        MockInvokeAdapter.return_value = MagicMock(
            backend_id='llama_cpp',
            model='llama-3.2-local',
            text='{"status":"ok"}',
            usage={'prompt_tokens': 7, 'completion_tokens': 3},
            raw_response={},
        )

        payload = {
            "message": "Return compact JSON only.",
            "model": "models/gemini-2.0-flash-exp",
            "backend_selector": {
                "preferred_backend_id": "llama_cpp",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "llama_cpp": {
                            "enabled": True,
                            "model": "llama-3.2-local",
                            "timeout_seconds": 12,
                            "headers": {
                                "X-Request-Id": "hb-runtime-profile"
                            },
                        }
                    }
                },
                "requirements": {
                    "require_tools": False,
                    "require_json_mode": True,
                    "require_streaming": False,
                },
            },
        }

        response = client.post(route_path, json=payload)

        if route_path == "/api/ai/chat":
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert data["backend_selection"]["resolved_backend_id"] == "llama_cpp"
        else:
            assert response.status_code == 200
            events = _parse_sse_data_events(response)
            complete_events = [evt for evt in events if evt.get("type") == "complete"]
            assert complete_events, events
            assert complete_events[-1]["success"] is True

        runtime_config = MockInvokeAdapter.call_args.kwargs["runtime_config"]
        llama_cfg = runtime_config["backends"]["llama_cpp"]

        assert llama_cfg["base_url"] == "http://session-llama"
        assert llama_cfg["enabled"] is True
        assert llama_cfg["model"] == "llama-3.2-local"
        assert llama_cfg["timeout_seconds"] == 12
        assert llama_cfg["headers"] == {
            "Authorization": "Bearer session-token",
            "X-Request-Id": "hb-runtime-profile",
        }


def test_ai_chat_runtime_failure_payload_includes_runtime_profile_source_and_precedence(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend', side_effect=RuntimeError('connection refused')), \
         patch('app.build_local_backend_readiness_diagnostic') as MockReadiness:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockReadiness.return_value = {
            'backend_id': 'llama_cpp',
            'status': 'unreachable',
            'readiness_code': 'backend_unreachable',
            'ready': False,
        }

        with client.session_transaction() as sess:
            sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
                'backends': {
                    'llama_cpp': {
                        'base_url': 'http://session-llama',
                        'timeout_seconds': 33,
                        'enabled': False,
                    }
                }
            }

        response = client.post('/api/ai/chat', json={
            'message': 'Return compact JSON.',
            'model': 'models/gemini-2.0-flash-exp',
            'backend_selector': {
                'preferred_backend_id': 'llama_cpp',
                'allow_fallback': False,
                'runtime_config': {
                    'backends': {
                        'llama_cpp': {
                            'enabled': True,
                            'model': 'llama-3.2-local',
                            'timeout_seconds': 9,
                        }
                    }
                },
                'requirements': {
                    'require_tools': False,
                    'require_json_mode': True,
                    'require_streaming': False,
                },
            },
        })

        assert response.status_code == 502
        data = response.get_json()
        assert data['success'] is False

        runtime_profile = data['backend_diagnostics']['runtime_profile']
        assert runtime_profile['source'] == 'session_profile_plus_request_overrides'
        assert runtime_profile['uses_session_profile'] is True
        assert runtime_profile['uses_request_overrides'] is True

        readiness_runtime_profile = data['backend_diagnostics']['readiness']['runtime_profile']
        assert readiness_runtime_profile['source'] == 'session_profile_plus_request_overrides'

        readiness_kwargs = MockReadiness.call_args.kwargs
        assert readiness_kwargs['session_runtime_config']['backends']['llama_cpp']['base_url'] == 'http://session-llama'
        assert readiness_kwargs['request_runtime_config']['backends']['llama_cpp']['timeout_seconds'] == 9


def test_ai_chat_stream_runtime_failure_payload_includes_runtime_profile_source_and_precedence(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.invoke_text_request_for_backend', side_effect=RuntimeError('stream runtime failure')), \
         patch('app.build_local_backend_readiness_diagnostic') as MockReadiness:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        MockReadiness.return_value = {
            'backend_id': 'llama_cpp',
            'status': 'unreachable',
            'readiness_code': 'backend_unreachable',
            'ready': False,
        }

        with client.session_transaction() as sess:
            sess[LOCAL_BACKEND_RUNTIME_CONFIG_SESSION_KEY] = {
                'backends': {
                    'llama_cpp': {
                        'base_url': 'http://session-llama',
                        'timeout_seconds': 33,
                        'enabled': False,
                    }
                }
            }

        response = client.post('/api/ai/chat/stream', json={
            'message': 'Return compact JSON.',
            'model': 'models/gemini-2.0-flash-exp',
            'backend_selector': {
                'preferred_backend_id': 'llama_cpp',
                'allow_fallback': False,
                'runtime_config': {
                    'backends': {
                        'llama_cpp': {
                            'enabled': True,
                            'model': 'llama-3.2-local',
                            'timeout_seconds': 9,
                        }
                    }
                },
                'requirements': {
                    'require_tools': False,
                    'require_json_mode': True,
                    'require_streaming': False,
                },
            },
        })

        assert response.status_code == 200
        events = _parse_sse_data_events(response)
        error_events = [evt for evt in events if evt.get('type') == 'error']
        assert error_events, events

        err = error_events[-1]
        assert err['success'] is False
        assert err['backend_selection']['execution_mode'] == 'local_text_adapter'

        runtime_profile = err['backend_diagnostics']['runtime_profile']
        assert runtime_profile['source'] == 'session_profile_plus_request_overrides'
        assert runtime_profile['uses_session_profile'] is True
        assert runtime_profile['uses_request_overrides'] is True

        readiness_runtime_profile = err['backend_diagnostics']['readiness']['runtime_profile']
        assert readiness_runtime_profile['source'] == 'session_profile_plus_request_overrides'

        readiness_kwargs = MockReadiness.call_args.kwargs
        assert readiness_kwargs['session_runtime_config']['backends']['llama_cpp']['base_url'] == 'http://session-llama'
        assert readiness_kwargs['request_runtime_config']['backends']['llama_cpp']['timeout_seconds'] == 9


def test_ai_chat_rejects_local_model_prefix_without_model_name(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'llama_cpp',
             'status': 'misconfigured',
             'readiness_code': 'invalid_models_payload',
             'ready': False,
         }):
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        payload = {
            "message": "Return JSON only.",
            "model": "llama_cpp::   ",
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Invalid local model selector" in data["error"]
        assert "llama_cpp::<model_name>" in data["error"]
        assert data["backend_diagnostics"]["failure_stage"] == "selector_validation"
        assert data["backend_diagnostics"]["error_code"] == "invalid_local_model_selector"
        assert data["backend_diagnostics"]["readiness"]["backend_id"] == "llama_cpp"
        assert data["backend_diagnostics"]["effective_capability_overrides"] == {
            "supports_tools": True,
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_streaming": True,
        }
        assert data["backend_diagnostics"]["readiness"]["effective_capability_overrides"] == {
            "supports_tools": True,
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_streaming": True,
        }
        assert data["backend_diagnostics"]["remediation"]["summary"] == "Local model selector is malformed."
        assert data["backend_diagnostics"]["remediation"]["action_codes"] == [
            "use_backend_model_selector_format",
            "select_nonempty_local_model_name",
        ]


@pytest.mark.parametrize("model_name", ["llama_cpp::llama-3.2-local", "lm_studio::qwen2.5"])
def test_ai_process_prompt_rejects_local_model_prefixes(client, model_name):
    with patch('app.get_project_manager_for_session') as MockPMGetter:
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        response = client.post("/ai_process_prompt", json={
            "prompt": "Build a detector.",
            "model": model_name,
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "One-shot AI generate currently supports Gemini/Ollama model ids only" in data["error"]


def test_manage_assembly_tool_auto_generates_placement_names_when_missing():
    evaluator = ExpressionEvaluator()
    pm = ProjectManager(evaluator)
    pm.create_empty_project()

    world_lv_ref = pm.current_geometry_state.world_volume_ref

    result = dispatch_ai_tool(pm, "manage_assembly", {
        "name": "asm_auto",
        "placements": [
            {
                "volume_ref": world_lv_ref,
                "position": {"x": "0", "y": "0", "z": "0"}
            }
        ]
    })

    assert result["success"] is True, result.get("error")

    asm = pm.current_geometry_state.assemblies.get("asm_auto")
    assert asm is not None
    assert len(asm.placements) == 1
    assert asm.placements[0].name.startswith("asm_auto_placement_")


def test_manage_assembly_tool_returns_validation_error_for_missing_volume_ref():
    evaluator = ExpressionEvaluator()
    pm = ProjectManager(evaluator)
    pm.create_empty_project()

    result = dispatch_ai_tool(pm, "manage_assembly", {
        "name": "asm_bad",
        "placements": [{}]
    })

    assert result["success"] is False
    assert "placements[0] is missing required field 'volume_ref'" in result.get("error", "")


def test_ai_analysis_summary_integration(client):
    """Verify that the analysis summary tool integration."""
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('h5py.File') as MockFile, \
         patch('os.path.exists', return_value=True):
        
        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        pm.current_version_id = "test-v"
        MockPMGetter.return_value = pm

        mock_f = MockFile.return_value.__enter__.return_value
        mock_hits = MagicMock()
        mock_f.__getitem__.side_effect = lambda k: mock_hits if k == 'default_ntuples/Hits' else MagicMock()
        mock_f.__contains__.side_effect = lambda k: k == 'default_ntuples/Hits'
        
        mock_entries = MagicMock()
        mock_entries.shape = ()
        mock_entries.__getitem__.return_value = 5
        
        mock_names = MagicMock()
        mock_names.__getitem__.return_value = [b"gamma"] * 5
        
        def hits_getitem(key):
            if key == 'entries': return mock_entries
            if key == 'ParticleName': return mock_names
            return MagicMock()
            
        mock_hits.__getitem__.side_effect = hits_getitem
        mock_hits.__contains__.side_effect = lambda k: k in ['entries', 'ParticleName']

        result = dispatch_ai_tool(pm, "get_analysis_summary", {"job_id": "test-job"})
        assert result['success'], f"Error: {result.get('error')}"
        assert result['summary']['total_hits'] == 5
        assert result['summary']['particle_breakdown']['gamma'] == 5
