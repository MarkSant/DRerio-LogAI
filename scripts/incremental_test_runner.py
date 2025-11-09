#!/usr/bin/env python3
"""
Incremental Test Runner - Executes tests one file at a time with progress tracking
to identify exactly which test causes system freezes.
"""
import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime

PROGRESS_FILE = Path("test_progress.json")
LOG_FILE = Path("test_execution.log")

def load_progress():
    """Load progress from file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"completed": [], "failed": [], "last_file": None, "started_at": None}

def save_progress(progress):
    """Save progress to file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def log(message):
    """Log message to both console and file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')

def get_test_files():
    """Get all non-GUI test files."""
    # Known problematic files that cause system freeze
    SKIP_FILES = {
        'test_live_camera_service_threading.py',
    }
    
    tests_dir = Path("tests")
    all_files = sorted([
        str(f) for f in tests_dir.glob("test_*.py")
        if f.is_file() and "manual" not in str(f) and f.name not in SKIP_FILES
    ])
    
    # Filter out GUI tests by checking file content
    non_gui_files = []
    for file_path in all_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(500)  # Check first 500 chars
            # Skip if it's explicitly marked as GUI or in ui/ subdirectory
            if '@pytest.mark.gui' not in content and '/ui/' not in file_path:
                non_gui_files.append(file_path)
    
    return non_gui_files

def run_single_test_file(test_file, file_num, total_files):
    """Run a single test file with timeout and monitoring."""
    log(f"\n{'='*80}")
    log(f"TEST FILE {file_num}/{total_files}: {test_file}")
    log(f"{'='*80}")
    
    cmd = [
        "poetry", "run", "pytest",
        test_file,
        "-v",
        "--tb=short",
        "-n=0",  # No parallelization
        "--maxfail=1",  # Stop on first failure
        "-x",  # Exit on first error
    ]
    
    try:
        log(f"Starting: {test_file}")
        start_time = time.time()
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 120 second timeout per file
            encoding='utf-8',
            errors='replace'
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            log(f"[OK] PASSED: {test_file} ({elapsed:.1f}s)")
            return "passed", None
        else:
            error_msg = result.stdout[-500:] if result.stdout else result.stderr[-500:]
            log(f"[FAIL] FAILED: {test_file} ({elapsed:.1f}s)")
            log(f"Error: {error_msg}")
            return "failed", error_msg
            
    except subprocess.TimeoutExpired:
        log(f"[TIMEOUT] {test_file} (exceeded 120 seconds)")
        log(f"WARNING: This file may cause system freeze!")
        return "timeout", "Test exceeded 120 second timeout"
        
    except Exception as e:
        log(f"[ERROR] {test_file} - {str(e)}")
        return "error", str(e)

def main():
    """Main test runner with incremental progress tracking."""
    log("\n" + "="*80)
    log("INCREMENTAL TEST RUNNER - Starting")
    log("="*80)
    
    # Load previous progress
    progress = load_progress()
    
    # Get all test files
    all_test_files = get_test_files()
    log(f"\nFound {len(all_test_files)} non-GUI test files")
    
    # Filter out already completed
    completed_set = set(progress.get("completed", []))
    remaining_files = [f for f in all_test_files if f not in completed_set]
    
    if completed_set:
        log(f"Resuming from previous run - {len(completed_set)} files already completed")
        log(f"Remaining files to test: {len(remaining_files)}")
    
    if not remaining_files:
        log("\n✓ All tests already completed!")
        return
    
    # Update start time if first run
    if not progress.get("started_at"):
        progress["started_at"] = datetime.now().isoformat()
        save_progress(progress)
    
    # Run each test file
    for i, test_file in enumerate(remaining_files, 1):
        total_num = len(completed_set) + i
        total_files = len(all_test_files)
        
        # Update last file being tested
        progress["last_file"] = test_file
        save_progress(progress)
        
        # Run the test
        status, error = run_single_test_file(test_file, total_num, total_files)
        
        # Record result
        if status == "passed":
            progress["completed"].append(test_file)
        elif status in ["failed", "error", "timeout"]:
            progress["failed"].append({
                "file": test_file,
                "status": status,
                "error": error,
                "timestamp": datetime.now().isoformat()
            })
        
        # Save progress after each test
        save_progress(progress)
        
        # Brief pause between tests
        time.sleep(1)
        
        # Extra warning for timeouts
        if status == "timeout":
            log("\nWARNING: TIMEOUT DETECTED - This file may freeze the system!")
            log(f"File: {test_file}")
            log("Continuing with next file...\n")
    
    # Final summary
    log("\n" + "="*80)
    log("TEST RUN SUMMARY")
    log("="*80)
    log(f"Total files: {len(all_test_files)}")
    log(f"Completed: {len(progress['completed'])}")
    log(f"Failed: {len(progress['failed'])}")
    
    if progress['failed']:
        log("\nFailed/Timeout files:")
        for failure in progress['failed']:
            log(f"  [{failure['status']}] {failure['file']}")
    
    if len(progress['completed']) == len(all_test_files):
        log("\n[SUCCESS] All tests completed successfully!")
        sys.exit(0)
    else:
        log(f"\nSome tests failed or timed out. Check {LOG_FILE} for details.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nWARNING: Interrupted by user. Progress has been saved.")
        log("Run again to resume from last test.")
        sys.exit(130)
