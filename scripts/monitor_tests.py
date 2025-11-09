#!/usr/bin/env python3
"""Monitor test progress without interrupting execution."""
import json
import time
from pathlib import Path
from datetime import datetime

PROGRESS_FILE = Path("test_progress.json")
LOG_FILE = Path("test_execution.log")

def monitor():
    print("Test Progress Monitor - Press Ctrl+C to stop monitoring (tests will continue)")
    print("="*80)

    last_count = 0
    same_count_iterations = 0

    while True:
        try:
            if PROGRESS_FILE.exists():
                with open(PROGRESS_FILE, 'r') as f:
                    progress = json.load(f)

                completed = len(progress.get('completed', []))
                failed = len(progress.get('failed', []))
                current = progress.get('last_file', 'N/A')
                started = progress.get('started_at', 'N/A')

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Status:")
                print(f"  Completed: {completed}/51")
                print(f"  Failed: {failed}")
                print(f"  Current: {current}")
                print(f"  Started: {started}")

                # Check if stuck
                if completed == last_count:
                    same_count_iterations += 1
                    if same_count_iterations >= 3:
                        print(f"\n  WARNING: No progress for {same_count_iterations * 30} seconds!")
                        print(f"  System may be frozen on: {current}")
                else:
                    same_count_iterations = 0

                last_count = completed

                # Show last few log lines
                if LOG_FILE.exists():
                    with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                        if lines:
                            print("\n  Last log entry:")
                            for line in lines[-2:]:
                                print(f"    {line.rstrip()}")

            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for progress file...")

            time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped. Tests continue in background.")
            break
        except Exception as e:
            print(f"Error reading progress: {e}")
            time.sleep(30)

if __name__ == "__main__":
    monitor()
