"""Orchestrators package.

Sprint 24+ - Extracted orchestrators from MainViewModel to reduce complexity.

This package contains specialized orchestrators for different workflows:
- UIStateController: UI state synchronization (Sprint 28)

Legacy orchestrators have been consolidated into Super Coordinators in `zebtrack.coordinators`.
"""

from zebtrack.orchestrators.ui_state_controller import UIStateController

__all__ = [
    "UIStateController",
]
