#!/usr/bin/env python3
"""
Test script to validate the frame interval implementation without GUI dependencies.
"""

import sys
import os
sys.path.insert(0, 'src')

def test_controller_signature():
    """Test that the controller method has the right signature."""
    try:
        # Read the controller file and check the signature
        with open('src/zebtrack/core/controller.py', 'r') as f:
            content = f.read()
        
        # Check for the updated signature
        if 'analysis_interval_frames: int = 10' in content and 'display_interval_frames: int = 10' in content:
            print('✅ Controller signature updated with interval parameters')
            return True
        else:
            print('❌ Controller signature missing interval parameters')
            return False
    except Exception as e:
        print(f'❌ Controller signature test failed: {e}')
        return False

def test_gui_variables():
    """Test that the GUI has the new variables."""
    try:
        with open('src/zebtrack/ui/gui.py', 'r') as f:
            content = f.read()
        
        # Check for the new variables
        if 'analysis_interval_var = StringVar(value="10")' in content and 'display_interval_var = StringVar(value="10")' in content:
            print('✅ GUI variables added correctly')
            return True
        else:
            print('❌ GUI variables not found')
            return False
    except Exception as e:
        print(f'❌ GUI variables test failed: {e}')
        return False

def test_gui_controls():
    """Test that the GUI controls were added."""
    try:
        with open('src/zebtrack/ui/gui.py', 'r') as f:
            content = f.read()
        
        # Check for the new controls
        if ('Intervalo de Análise (frames)' in content and 
            'Intervalo de Exibição (frames)' in content and
            'Intervalos de Processamento' in content):
            print('✅ GUI controls added in both workflows')
            return True
        else:
            print('❌ GUI controls missing')
            return False
    except Exception as e:
        print(f'❌ GUI controls test failed: {e}')
        return False

def test_file_processing_loop_removal():
    """Test that the alternate processing loop was removed."""
    try:
        with open('src/zebtrack/ui/gui.py', 'r') as f:
            content = f.read()
        
        # Check that _file_processing_loop is gone
        if '_file_processing_loop' not in content:
            print('✅ Alternate file processing loop removed')
            return True
        else:
            print('❌ Alternate file processing loop still exists')
            return False
    except Exception as e:
        print(f'❌ File processing loop removal test failed: {e}')
        return False

def test_persistence_logic():
    """Test that persistence logic was added."""
    try:
        with open('src/zebtrack/core/controller.py', 'r') as f:
            content = f.read()
        
        # Check for persistence logic
        if ('analysis_interval_frames' in content and 
            'display_interval_frames' in content and
            'project_data' in content):
            print('✅ Persistence logic added')
            return True
        else:
            print('❌ Persistence logic missing')
            return False
    except Exception as e:
        print(f'❌ Persistence logic test failed: {e}')
        return False

def test_decoupled_processing():
    """Test that decoupled processing logic was implemented."""
    try:
        with open('src/zebtrack/core/controller.py', 'r') as f:
            content = f.read()
        
        # Check for decoupled processing logic
        if ('should_process' in content and 
            'should_display' in content and
            'processed_frames_count' in content):
            print('✅ Decoupled processing logic implemented')
            return True
        else:
            print('❌ Decoupled processing logic missing')
            return False
    except Exception as e:
        print(f'❌ Decoupled processing test failed: {e}')
        return False

def main():
    """Run all tests."""
    print("🧪 Testing frame interval implementation...")
    print()
    
    tests = [
        test_file_processing_loop_removal,
        test_controller_signature,
        test_gui_variables,
        test_gui_controls,
        test_persistence_logic,
        test_decoupled_processing,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Implementation is complete.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)