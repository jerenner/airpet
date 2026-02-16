import pytest
import requests
import json
import time
import subprocess
import os

BASE_URL = "http://127.0.0.1:5003"

@pytest.fixture(scope="module")
def flask_server():
    # Start the flask server in a subprocess
    process = subprocess.Popen(
        ["/Users/marth/miniconda/envs/airpet/bin/python", "app.py"],
        cwd="/Users/marth/projects/airpet",
        env={**os.environ, "FLASK_RUN_PORT": "5003", "APP_MODE": "local"}
    )
    time.sleep(3) # Wait for startup
    yield
    process.terminate()

def test_ai_chat_flow(flask_server):
    # 1. Clear history first
    res = requests.post(f"{BASE_URL}/api/ai/clear")
    assert res.status_code == 200

    # 2. Send a message to create geometry
    # Note: We use a model ID that the backend supports
    payload = {
        "message": "Create a variable 'box_size' set to 100, then create a box named 'MainBox' with that size and place it in the center of the World.",
        "model": "models/gemini-2.0-flash-exp" # Or whatever is available
    }
    
    # We need a session to keep the project state consistent if we weren't in 'local' mode
    # but in local mode, one PM is shared.
    response = requests.post(f"{BASE_URL}/api/ai/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data['success']
    
    # 3. Verify project state
    state_res = requests.get(f"{BASE_URL}/get_project_state")
    state = state_res.json()['project_state']
    
    assert 'box_size' in state['defines']
    assert 'MainBox' in state['solids']
    
    # 4. Check history
    hist_res = requests.get(f"{BASE_URL}/api/ai/history")
    history = hist_res.json()['history']
    # 2 initial + 1 user + 1 model + (potential tool results turns)
    assert len(history) >= 4 
    
    # Verify the last message contains an explanation
    last_msg = history[-1]
    assert last_msg['role'] == 'model'
    # Text is in 'parts'
    text = "".join([p.get('text', '') for p in last_msg['parts']])
    assert len(text) > 0

def test_ai_search_integration(flask_server):
    # Ensure there's a box to find
    requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": "Create a solid called 'Shielding_Wall' with x=10, y=200, z=200",
        "model": "models/gemini-2.0-flash-exp"
    })
    
    # Search for it
    payload = {
        "message": "Search for all solids with 'Shielding' in their name and tell me if you find any.",
        "model": "models/gemini-2.0-flash-exp"
    }
    response = requests.post(f"{BASE_URL}/api/ai/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Shielding_Wall" in data['message']
