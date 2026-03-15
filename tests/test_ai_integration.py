import pytest
import json
from unittest.mock import MagicMock, patch
from app import app, dispatch_ai_tool
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


def test_ai_chat_backend_selector_surfaces_fallback_diagnostics_in_success_response(client):
    final_part = MagicMock()
    final_part.function_call = None
    final_part.text = "Selection fallback succeeded."

    final_response = MagicMock()
    final_response.candidates = [MagicMock()]
    final_response.candidates[0].content.parts = [final_part]
    final_response.candidates[0].content.role = "model"
    final_response.text = "Selection fallback succeeded."

    with patch('app.get_gemini_client_for_session') as MockClientGetter, \
         patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.types.GenerateContentConfig', side_effect=lambda **kwargs: kwargs), \
         patch('app.time.sleep', return_value=None):

        evaluator = ExpressionEvaluator()
        pm = ProjectManager(evaluator)
        pm.create_empty_project()
        MockPMGetter.return_value = pm

        mock_client = MagicMock()
        MockClientGetter.return_value = mock_client
        mock_client.models.generate_content.return_value = final_response

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
        assert data["backend_selection"]["resolved_backend_id"] == "gemini_remote"
        assert data["backend_selection"]["used_fallback"] is True
        assert data["backend_selection"]["tried"][0]["backend_id"] == "llama_cpp"
        assert data["backend_selection"]["tried"][0]["missing_capabilities"] == ["tools"]


def test_ai_chat_backend_selector_returns_deterministic_no_fallback_error(client):
    with patch('app.get_project_manager_for_session') as MockPMGetter, \
         patch('app.build_local_backend_readiness_diagnostic', return_value={
             'backend_id': 'llama_cpp',
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
                "preferred_backend_id": "llama_cpp",
                "allow_fallback": False,
                "runtime_config": {
                    "backends": {
                        "llama_cpp": {"enabled": True},
                        "lm_studio": {"enabled": True}
                    }
                },
                "requirements": {
                    "require_tools": True,
                    "require_json_mode": True
                }
            }
        }

        response = client.post("/api/ai/chat", json=payload)

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "AI backend selection failed" in data["error"]
        assert data["backend_selection"]["preferred_backend_id"] == "llama_cpp"
        assert data["backend_selection"]["allow_fallback"] is False
        assert "'backend_id': 'llama_cpp'" in data["backend_selection"]["selection_error"]
        assert "'missing_capabilities': ['tools']" in data["backend_selection"]["selection_error"]
        assert data["backend_diagnostics"]["failure_stage"] == "selector_requirements"
        assert data["backend_diagnostics"]["error_code"] == "backend_selection_failed"
        assert data["backend_diagnostics"]["readiness"]["status"] == "healthy"


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
                            "base_url": "http://localhost:1234"
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
        assert invocation_request.require_tools is False
        assert invocation_request.require_json_mode is True
        assert invocation_request.require_streaming is False


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
