#!/usr/bin/env python3
"""Test script for mode persistence robustness"""

import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_load_mode():
    """Test load_mode function with various scenarios"""
    
    # Import after path setup
    from main import load_mode, save_mode, CONFIG_FILE
    
    print("=" * 60)
    print("Testing Mode Persistence Robustness")
    print("=" * 60)
    
    # Test 1: Valid mode (planning)
    print("\n[Test 1] Valid mode: 'planning'")
    config = {'portfolio_size': 10000.0, 'mode': 'planning'}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    result = load_mode()
    assert result == 'planning', f"Expected 'planning', got '{result}'"
    print(f"  ✓ Mode loaded correctly: {result}")
    
    # Test 2: Valid mode (live)
    print("\n[Test 2] Valid mode: 'live'")
    config = {'portfolio_size': 10000.0, 'mode': 'live'}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    result = load_mode()
    assert result == 'live', f"Expected 'live', got '{result}'"
    print(f"  ✓ Mode loaded correctly: {result}")
    
    # Test 3: Invalid mode value
    print("\n[Test 3] Invalid mode: 'invalid_mode'")
    config = {'portfolio_size': 10000.0, 'mode': 'invalid_mode'}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    result = load_mode()
    assert result == 'planning', f"Expected 'planning' (fallback), got '{result}'"
    print(f"  ✓ Invalid mode defaulted to: {result}")
    # Check if warning was printed (already shown above)
    # Verify config was corrected
    with open(CONFIG_FILE, 'r') as f:
        corrected = json.load(f)
    assert corrected['mode'] == 'planning', "Config should be corrected"
    print(f"  ✓ Config was corrected to planning")
    
    # Test 4: Corrupt JSON
    print("\n[Test 4] Corrupt JSON file")
    with open(CONFIG_FILE, 'w') as f:
        f.write('not valid json {')
    result = load_mode()
    assert result == 'planning', f"Expected 'planning' (fallback), got '{result}'"
    print(f"  ✓ Corrupt JSON defaulted to: {result}")
    
    # Test 5: Missing mode key
    print("\n[Test 5] Missing mode key in config")
    config = {'portfolio_size': 10000.0}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    result = load_mode()
    assert result == 'planning', f"Expected 'planning' (default), got '{result}'"
    print(f"  ✓ Missing mode defaulted to: {result}")
    
    # Test 6: Empty config file
    print("\n[Test 6] Empty config file")
    with open(CONFIG_FILE, 'w') as f:
        f.write('')
    result = load_mode()
    assert result == 'planning', f"Expected 'planning' (default), got '{result}'"
    print(f"  ✓ Empty config defaulted to: {result}")
    
    # Test 7: Non-existent config file
    print("\n[Test 7] Non-existent config file")
    os.remove(CONFIG_FILE)
    result = load_mode()
    assert result == 'planning', f"Expected 'planning' (default), got '{result}'"
    print(f"  ✓ Non-existent file defaulted to: {result}")
    
    # Test 8: Mode change takes effect immediately
    print("\n[Test 8] Mode change takes effect immediately")
    config = {'portfolio_size': 10000.0, 'mode': 'planning'}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    result1 = load_mode()
    assert result1 == 'planning'
    print(f"  Initial mode: {result1}")
    
    # Change mode
    save_mode('live')
    result2 = load_mode()
    assert result2 == 'live', f"Expected 'live' after save, got '{result2}'"
    print(f"  ✓ Mode changed to: {result2}")
    
    # Change back to planning
    save_mode('planning')
    result3 = load_mode()
    assert result3 == 'planning', f"Expected 'planning' after save, got '{result3}'"
    print(f"  ✓ Mode changed back to: {result3}")
    
    # Restore valid config
    print("\n[Cleanup] Restoring valid config")
    config = {'portfolio_size': 10000.0, 'mode': 'planning'}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    
    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)

if __name__ == '__main__':
    test_load_mode()
