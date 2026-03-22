#!/usr/bin/env python3
"""Test trap solid via AI chat"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5003"

def main():
    # Start fresh project
    print("Creating new project...")
    requests.post(f"{BASE_URL}/new_project", json={})
    time.sleep(1)
    
    # Test trap via AI with all parameters specified
    print("\n" + "="*60)
    print("Test: Create trap solid via AI")
    print("="*60)
    
    message = """Create a trap solid named test_trap with these parameters:
- z: 100mm
- y1: 20mm
- x1: 10mm
- x2: 15mm
- y2: 25mm
- x3: 12mm
- x4: 18mm
(Use default values for theta, phi, alpha1, alpha2)"""
    
    print(f"\nMessage: {message}")
    print("-"*60)
    
    try:
        start = time.time()
        response = requests.post(
            f"{BASE_URL}/api/ai/chat",
            json={
                "message": message,
                "model": "llama_cpp::Qwen3.5-27B-Q6_K",
                "turn_limit": 50
            },
            timeout=600  # 10 minute timeout
        )
        elapsed = time.time() - start
        
        print(f"\nResponse time: {elapsed:.1f}s")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            message_text = result.get('message', 'No message')
            print(f"\nAI Response: {message_text[:300]}")
            
            # Check if solid was created
            project_state = result.get('project_state', {})
            solids = project_state.get('solids', {})
            
            if 'test_trap' in solids:
                print(f"\n✅ Solid 'test_trap' created successfully!")
                print(f"   Type: {solids['test_trap'].get('type')}")
                print(f"   Parameters: {json.dumps(solids['test_trap'].get('raw_parameters', {}), indent=4)}")
                return True
            else:
                print(f"\n❌ Solid 'test_trap' NOT found")
                print(f"Available solids: {list(solids.keys())}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ TIMEOUT after 600 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
