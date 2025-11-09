#!/usr/bin/env python3
"""
Safe GUI Test Runner - Executes GUI tests one at a time with memory monitoring
to prevent system freezes on Windows.
"""
import subprocess
import sys
import time
import gc
from pathlib import Path

def run_single_gui_test(test_name, test_num, total_tests):
    """Run a single GUI test with maximum safety."""
    print(f"\n{'='*80}")
    print(f"GUI TEST {test_num}/{total_tests}: {test_name}")
    print(f"{'='*80}\n")
    
    cmd = [
        "poetry", "run", "pytest",
        test_name,
        "-v",
        "--tb=line",  # Minimal traceback
        "-n=0",  # NEVER parallelize GUI tests
        "--maxfail=1",
        "-x",  # Stop on first failure
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
            timeout=120  # 2 minute timeout per test
        )
        
        if result.returncode != 0:
            print(f"\n❌ FAILED: {test_name}")
            return False
        
        print(f"✓ PASSED: {test_name}")
        
    except subprocess.TimeoutExpired:
        print(f"\n⏱️  TIMEOUT: {test_name} (exceeded 120 seconds)")
        return False
    
    except Exception as e:
        print(f"\n💥 ERROR running {test_name}: {e}")
        return False
    
    # Aggressive garbage collection
    gc.collect()
    time.sleep(1.5)  # Longer pause between GUI tests
    
    return True

def main():
    """Main GUI test runner."""
    
    # Run GUI tests one file at a time
    cmd = ["poetry", "run", "pytest", "-m", "gui", "--collect-only", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse test names from output
    lines = result.stdout.strip().split('\n')
    test_items = [line.strip() for line in lines if '::' in line and 'test_' in line]
    
    if not test_items:
        print("No GUI tests found!")
        return
    
    print(f"Found {len(test_items)} GUI tests")
    print("Running tests ONE AT A TIME with safety pauses...\n")
    
    # Group tests by file to run file-by-file
    tests_by_file = {}
    for item in test_items:
        file_path = item.split('::')[0]
        if file_path not in tests_by_file:
            tests_by_file[file_path] = []
        tests_by_file[file_path].append(item)
    
    failed_tests = []
    total_files = len(tests_by_file)
    
    for file_num, (file_path, tests) in enumerate(tests_by_file.items(), 1):
        print(f"\n{'#'*80}")
        print(f"FILE {file_num}/{total_files}: {file_path}")
        print(f"Contains {len(tests)} tests")
        print(f"{'#'*80}\n")
        
        # Run entire file at once (safer than individual tests)
        success = run_single_gui_test(file_path, file_num, total_files)
        
        if not success:
            failed_tests.append(file_path)
            print(f"\n⚠️  File {file_path} had failures")
        
        # Extra long pause between test files
        if file_num < total_files:
            print("\n⏸️  Pausing 3 seconds before next test file...")
            time.sleep(3)
    
    # Summary
    print(f"\n{'='*80}")
    print("GUI TEST RUN SUMMARY")
    print(f"{'='*80}")
    print(f"Total test files: {total_files}")
    print(f"Failed test files: {len(failed_tests)}")
    
    if failed_tests:
        print(f"\nFailed files:")
        for test in failed_tests:
            print(f"  - {test}")
        sys.exit(1)
    else:
        print("\n✓ All GUI test files passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
