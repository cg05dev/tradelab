#!/usr/bin/env python3
"""Test script for mode API endpoints"""

import json
import os
import sys
import time
import subprocess
import requests

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_api():
    """Test mode API endpoints"""
    print("=" * 60)
    print("Testing Mode API Endpoints")
    print("=" * 60)
    
    # First, restore valid config
    config = {'portfolio_size': 10000.0, 'mode': 'planning'}
    with open('portfolio_config.json', 'w') as f:
        json.dump(config, f)
    print("\n[Setup] Restored valid config with planning mode")
    
    # Start backend in background
    print("\n[Setup] Starting backend server...")
    backend_process = subprocess.Popen(
        ['./venv/bin/python', 'main.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(3)  # Wait for server to start
    
    try:
        # Test 1: GET /api/mode - should return planning by default
        print("\n[Test 1] GET /api/mode - default planning mode")
        response = requests.get('http://127.0.0.1:8000/api/mode')
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning', got '{data['mode']}'"
        print(f"  ✓ Mode is: {data['mode']}")
        
        # Test 2: POST /api/mode - switch to live
        print("\n[Test 2] POST /api/mode - switch to live")
        response = requests.post(
            'http://127.0.0.1:8000/api/mode',
            json={'mode': 'live'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'live', f"Expected 'live', got '{data['mode']}'"
        print(f"  ✓ Mode changed to: {data['mode']}")
        
        # Test 3: GET /api/mode - verify mode persisted
        print("\n[Test 3] GET /api/mode - verify mode persisted")
        response = requests.get('http://127.0.0.1:8000/api/mode')
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'live', f"Expected 'live' after persistence, got '{data['mode']}'"
        print(f"  ✓ Mode is still: {data['mode']}")
        
        # Test 4: POST /api/mode - switch back to planning
        print("\n[Test 4] POST /api/mode - switch back to planning")
        response = requests.post(
            'http://127.0.0.1:8000/api/mode',
            json={'mode': 'planning'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning', got '{data['mode']}'"
        print(f"  ✓ Mode changed to: {data['mode']}")
        
        # Test 5: POST /api/mode with invalid value - should return 400
        print("\n[Test 5] POST /api/mode - invalid value should return 400")
        response = requests.post(
            'http://127.0.0.1:8000/api/mode',
            json={'mode': 'invalid_mode'}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert 'detail' in data
        print(f"  ✓ Invalid mode rejected with 400")
        
        # Test 6: GET /api/mode - verify mode unchanged after invalid attempt
        print("\n[Test 6] GET /api/mode - verify mode unchanged after invalid attempt")
        response = requests.get('http://127.0.0.1:8000/api/mode')
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning', got '{data['mode']}'"
        print(f"  ✓ Mode is still: {data['mode']}")
        
        # Test 7: Read-only endpoints work in planning mode
        print("\n[Test 7] Read-only endpoints work in planning mode")
        response = requests.get('http://127.0.0.1:8000/api/portfolio')
        assert response.status_code == 200
        print(f"  ✓ GET /api/portfolio returns 200")
        
        response = requests.get('http://127.0.0.1:8000/api/trades/open')
        assert response.status_code == 200
        print(f"  ✓ GET /api/trades/open returns 200")
        
        response = requests.get('http://127.0.0.1:8000/api/analytics/overview')
        assert response.status_code == 200
        print(f"  ✓ GET /api/analytics/overview returns 200")
        
        # Test 8: Execution endpoint blocked in planning mode
        print("\n[Test 8] Execution endpoint blocked in planning mode")
        response = requests.post(
            'http://127.0.0.1:8000/api/hyperliquid/order',
            json={
                'coin': 'BTC',
                'is_buy': True,
                'margin_amount': 100,
                'leverage': 10,
                'entry_price': 50000
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        # Check for mode_blocked error (may be in 'detail' or 'error')
        detail = data.get('detail', data.get('error', ''))
        print(f"  Detail: {detail}")
        assert 'mode_blocked' in str(detail) or 'planning' in str(detail), f"Expected mode_blocked, got {detail}"
        print(f"  ✓ Execution blocked in planning mode (403)")
        
        print("\n" + "=" * 60)
        print("All API tests passed!")
        print("=" * 60)
        
    finally:
        # Cleanup
        print("\n[Cleanup] Stopping backend server...")
        backend_process.terminate()
        backend_process.wait()
        
        # Restore valid config
        config = {'portfolio_size': 10000.0, 'mode': 'planning'}
        with open('portfolio_config.json', 'w') as f:
            json.dump(config, f)

if __name__ == '__main__':
    test_api()
