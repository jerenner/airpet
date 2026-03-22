#!/usr/bin/env python3
"""Test complex solids via AI chat - Tests 48-49"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5003"

def test_ai_complex_solid(test_name, message, expected_solid):
    """Test creating a complex solid via AI chat"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Message: {message}")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/ai/chat",
            json={
                "message": message,
                "model": "llama_cpp::Qwen3.5-27B-Q6_K",
                "turn_limit": 50  # Increased for complex solids with many parameters
            },
            timeout=600  # 10 minute timeout for more turns
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ AI Response: {result.get('message', 'No response text')[:200]}")
            
            # Check if solid was created from the AI response itself
            project_state = result.get('project_state', {})
            solids = project_state.get('solids', {})
            
            if expected_solid in solids:
                print(f"✅ Solid '{expected_solid}' created successfully")
                print(f"   Type: {solids[expected_solid].get('type')}")
                print(f"   Parameters: {json.dumps(solids[expected_solid].get('raw_parameters', {}), indent=4)}")
                return True
            else:
                print(f"❌ Solid '{expected_solid}' NOT found in project state")
                print(f"Available solids: {list(solids.keys())}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ TIMEOUT after 300 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_direct_api_solid(test_name, solid_name, solid_type, params):
    """Test creating a solid via direct API"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name} (Direct API)")
    print(f"Solid: {solid_name}, Type: {solid_type}")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/add_primitive_solid",
            json={
                "name": solid_name,
                "type": solid_type,
                "params": params
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Solid created: {result}")
            return True
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    # Start fresh project
    print("Creating new project...")
    requests.post(f"{BASE_URL}/new_project", json={})
    time.sleep(1)
    
    results = {}
    
    # Test 48: Polyhedra via Direct API (should work)
    results["48_direct"] = test_direct_api_solid(
        "Test 48 Direct API",
        "polyhedra_solid",
        "genericPolyhedra",
        {
            "numsides": "6",
            "startphi": "0*deg",
            "deltaphi": "360*deg",
            "rzpoints": [{"r": "10", "z": "-50"}, {"r": "50", "z": "50"}]
        }
    )
    
    # Test 48: Polyhedra via AI Chat (currently fails)
    results["48_ai"] = test_ai_complex_solid(
        "Test 48 AI Chat",
        "Create a genericPolyhedra solid named polyhedra_ai with 6 sides, startphi 0 deg, deltaphi 360 deg, and rzpoints: [{r: 10mm, z: -50mm}, {r: 50mm, z: 50mm}]",
        "polyhedra_ai"
    )
    
    # Test 49: Trapezoid via Direct API (should work)
    results["49_direct"] = test_direct_api_solid(
        "Test 49 Direct API",
        "trapezoid_solid",
        "trap",
        {
            "dz": "50",
            "theta": "0*deg",
            "phi": "0*deg",
            "x1": "20",
            "y1": "15",
            "x2": "10",
            "y2": "8",
            "alpha1": "0*deg",
            "alpha2": "0*deg",
            "alpha3": "0*deg",
            "alpha4": "0*deg"
        }
    )
    
    # Test 49: Trapezoid via AI Chat (currently fails)
    results["49_ai"] = test_ai_complex_solid(
        "Test 49 AI Chat",
        "Create a trap (trapezoid) solid named trapezoid_ai with dz=50mm, theta=0 deg, phi=0 deg, x1=20mm, y1=15mm, x2=10mm, y2=8mm, alpha1=0 deg, alpha2=0 deg, alpha3=0 deg, alpha4=0 deg",
        "trapezoid_ai"
    )
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
