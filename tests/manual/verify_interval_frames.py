"""Legacy manual check retained only for discoverability.

This script is no longer needed because `pytest -k interval_frames_config`
now covers the same assertions with real workflows. Running it prints a
guidance message and exits successfully to keep older docs accurate.
"""

import sys


def main() -> int:
    print(
        "The interval-frame validation is now automated. Run: "
        "pytest tests/test_interval_frames_config.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
