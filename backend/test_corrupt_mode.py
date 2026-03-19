#!/usr/bin/env python3
"""Test script for corrupt mode handling"""

import json
import os
import sys
import time
import subprocess

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_corrupt_mode():
    """Test corrupt/invalid mode handling"""
    print("=" * 60)
    print("Testing Corrupt Mode Handling")
    print("=" * 60)
    
    # Restore valid config
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
        import requests
        
        # Test 1: Valid mode via API
        print("\n[Test 1] Valid mode via API")
        response = requests.get('http://127.0.0.1:8000/api/mode')
        data = response.json()
        assert data['mode'] == 'planning'
        print(f"  ✓ Mode is: {data['mode']}")
        
        # Test 2: Corrupt JSON in config file
        print("\n[Test 2] Corrupt JSON in config file")
        with open('portfolio_config.json', 'w') as f:
            f.write('not valid json {')
        
        # Restart backend to reload config
        print("  Restarting backend...")
        backend_process.terminate()
        backend_process.wait()
        
        backend_process = subprocess.Popen(
            ['./venv/bin/python', 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(3)
        
        response = requests.get('http://127.0.0.1:8000/api/mode')
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning' (fallback), got '{data['mode']}'"
        print(f"  ✓ Mode fell back to: {data['mode']}")
        
        # Test 3: Invalid mode value
        print("\n[Test 3] Invalid mode value in config")
        with open('portfolio_config.json', 'w') as f:
            json.dump({'portfolio_size': 10000.0, 'mode': 'invalid_mode'}, f)
        
        # Restart backend
        print("  Restarting backend...")
        backend_process.terminate()
        backend_process.wait()
        
        backend_process = subprocess.Popen(
            ['./venv/bin/python', 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(3)
        
        response = requests.get('http://127.0.0.1:8000/api/mode')
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning' (fallback), got '{data['mode']}'"
        print(f"  ✓ Mode fell back to: {data['mode']}")
        
        # Test 4: Missing mode key
        print("\n[Test 4] Missing mode key in config")
        with open('portfolio_config.json', 'w') as f:
            json.dump({'portfolio_size': 10000.0}, f)
        
        # Restart backend
        print("  Restarting backend...")
        backend_process.terminate()
        backend_process.wait()
        
        backend_process = subprocess.Popen(
            ['./venv/bin/python', 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(3)
        
        response = requests.get('http://127.0.0.1:8000/api/mode')
        data = response.json()
        assert data['mode'] == 'planning', f"Expected 'planning' (default), got '{data['mode']}'"
        print(f"  ✓ Mode defaulted to: {data['mode']}")
        
        # Test 5: Verify config was corrected
        print("\n[Test 5] Verify config was corrected after invalid modes")
        # First verify the API returns correct mode
        try:
            response = requests.get('http://127.0.0.1:8000/api/mode')
            data = response.json()
            assert data['mode'] == 'planning', f"Expected 'planning', got '{data['mode']}'"
            print(f"  ✓ API reports mode: {data['mode']}")
        except Exception as e:
            print(f"  ! API call failed: {e}")
        
        # Then check the config file was fixed
        with open('portfolio_config.json', 'r') as f:
            config = json.load(f)
        print(f"  Config file contents: {config}")
        assert 'mode' in config, "Config should have mode key"
        assert config['mode'] == 'planning', "Config should be corrected to planning"
        print(f"  ✓ Config file corrected to: {config['mode']}")
        
        print("\n" + "=" * 60)
        print("All corrupt mode tests passed!")
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
    test_corrupt_mode()
