#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe Test Runner - Executes tests in small batches with memory management
to prevent system freezes on Windows.
"""
import subprocess
import sys
import time
import gc
from pathlib import Path

# Fix console encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def run_test_batch(test_files, batch_num, total_batches):
    """Run a single batch of tests with memory cleanup."""
    print(f"\n{'='*80}")
    print(f"BATCH {batch_num}/{total_batches}: Running {len(test_files)} test files")
    print(f"{'='*80}\n")

    for test_file in test_files:
        print(f"\n--- Testing: {test_file.name} ---")

        cmd = [
            "poetry", "run", "pytest",
            str(test_file),
            "-v",
            "--tb=short",
            "--maxfail=1",
            "-x",  # Stop on first failure
            "-n=0",  # No parallelization
        ]

        result = subprocess.run(cmd, capture_output=False)

        if result.returncode != 0:
            print(f"\n[FAIL] {test_file.name}")
            print(f"Stopping due to failure in {test_file.name}")
            return False

        print(f"[OK] {test_file.name}")

        # Force garbage collection after each test file
        gc.collect()
        time.sleep(0.5)  # Brief pause between files

    # Longer pause between batches
    print(f"\n[OK] Batch {batch_num} complete. Pausing for memory cleanup...")
    gc.collect()
    time.sleep(2)

    return True

def main():
    """Main test runner."""
    tests_dir = Path("tests")

    # Get all test files, excluding manual tests
    test_files = sorted([
        f for f in tests_dir.glob("test_*.py")
        if f.is_file() and "manual" not in str(f)
    ])

    print(f"Found {len(test_files)} test files")

    # Split into batches of 3 files each
    batch_size = 3
    batches = [test_files[i:i+batch_size] for i in range(0, len(test_files), batch_size)]

    total_batches = len(batches)
    print(f"Splitting into {total_batches} batches of up to {batch_size} files each\n")

    failed_batches = []

    for i, batch in enumerate(batches, 1):
        success = run_test_batch(batch, i, total_batches)

        if not success:
            failed_batches.append(i)
            print(f"\n[WARN] Batch {i} failed. Continuing to next batch...\n")
            time.sleep(3)  # Extra pause after failure

    # Summary
    print(f"\n{'='*80}")
    print("TEST RUN SUMMARY")
    print(f"{'='*80}")
    print(f"Total batches: {total_batches}")
    print(f"Failed batches: {len(failed_batches)}")

    if failed_batches:
        print(f"Failed batch numbers: {failed_batches}")
        sys.exit(1)
    else:
        print("[OK] All batches passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
