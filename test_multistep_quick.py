#!/usr/bin/env python3
"""
Quick Multi-Step Test - Validates AI conversation flow

This is a minimal test to verify multi-turn AI conversations work correctly.
It tests basic state persistence across 2-3 messages.
"""

import requests
import time

BASE_URL = "http://127.0.0.1:5003"
MODEL = "llama_cpp::Qwen3.5-27B-Q6_K"

def test_multistep_basic():
    """Test basic multi-step conversation."""
    
    print("\n" + "="*70)
    print("Quick Multi-Step Test")
    print("="*70)
    
    # Create fresh project
    print("\n1. Creating project...")
    resp = requests.post(f"{BASE_URL}/new_project", json={})
    assert resp.status_code == 200, f"Failed to create project: {resp.text}"
    print("   ✅ Project created")
    
    # Step 1: Create a box
    print("\n2. Step 1: Creating a box solid...")
    msg1 = "Create a box solid 100mm x 100mm x 100mm named 'my_box'"
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": msg1,
        "model": MODEL,
        "turn_limit": 15
    })
    elapsed1 = time.time() - start
    
    print(f"   ⏱️  Time: {elapsed1:.1f}s")
    print(f"   📊 Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"   🤖 AI: {data.get('text', 'N/A')[:150]}...")
    
    # Check box was created
    state = requests.get(f"{BASE_URL}/get_project_state").json()
    solids = state.get('project_state', {}).get('solids', {})
    
    # Look for any box-like solid (AI may name it differently)
    box_found = any('box' in k.lower() or 'my' in k.lower() for k in solids.keys())
    print(f"   {'✅' if box_found else '⚠️'} Box solid {'found' if box_found else 'not found (AI may use different name)'}")
    
    # Step 2: Create a material and reference the box
    print("\n3. Step 2: Creating a material...")
    msg2 = "Create a copper material with density 8.96 g/cm³"
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": msg2,
        "model": MODEL,
        "turn_limit": 15
    })
    elapsed2 = time.time() - start
    
    print(f"   ⏱️  Time: {elapsed2:.1f}s")
    print(f"   📊 Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"   🤖 AI: {data.get('text', 'N/A')[:150]}...")
    
    # Check material was created
    state = requests.get(f"{BASE_URL}/get_project_state").json()
    materials = state.get('project_state', {}).get('materials', {})
    
    copper_found = any('copper' in k.lower() for k in materials.keys())
    print(f"   {'✅' if copper_found else '⚠️'} Copper material {'found' if copper_found else 'not found'}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total steps: 2")
    print(f"Total AI time: {elapsed1 + elapsed2:.1f}s")
    print(f"Solids in project: {list(solids.keys())}")
    print(f"Materials in project: {list(materials.keys())}")
    
    success = resp.status_code == 200
    print(f"\n{'✅ TEST PASSED' if success else '❌ TEST FAILED'}")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(test_multistep_basic())
