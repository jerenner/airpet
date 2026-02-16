import pytest
import json
from unittest.mock import MagicMock, patch
from app import app, dispatch_ai_tool
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

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
         patch('app.get_project_manager_for_session') as MockPMGetter:
        
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

def test_ai_analysis_summary_integration(client):
    """Verify the analysis summary tool integration."""
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
