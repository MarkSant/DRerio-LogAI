"""The detector-settings flow must deliver its failures to a handler.

Clicking "Apply" with an out-of-range value used to do nothing at all: the
panel caught pydantic's ``ValidationError``, the coordinator raised
``DetectorSetupCoordinatorError`` (a bare ``Exception`` subclass at the time),
and the two are unrelated types. Nothing else caught it either — 31 raise sites
across ``coordinators/`` had zero handlers in ``src/`` — so the exception ended
up in Tk's default ``report_callback_exception``, which prints to a stderr the
packaged app does not have.

What these tests pin down:

* the type split — a value the user typed is ``ValidationError`` (user-facing
  message), anything else is ``DetectorSetupCoordinatorError`` (log message);
* both are reachable by ``except ZebTrackError``, so the hierarchy is catchable
  as one thing;
* there is exactly one ``ValidationError`` class, not one per import path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import zebtrack.core.exceptions as core_exceptions
import zebtrack.exceptions as public_exceptions
from zebtrack.coordinators.base_coordinator import (
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.coordinators.detector_setup_coordinator import (
    DetectorSetupCoordinator,
    DetectorSetupCoordinatorError,
)
from zebtrack.core.exceptions import ValidationError, ZebTrackError

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def detector_service():
    service = MagicMock()
    service.update_tracking_parameters.return_value = True
    service.settings = MagicMock()
    return service


@pytest.fixture
def coordinator(detector_service):
    state_manager = MagicMock()
    state_manager.get_state.return_value = {}
    state_manager.prefer_unified_state_api = True
    return DetectorSetupCoordinator(
        state_manager=state_manager,
        detector_service=detector_service,
        event_bus=MagicMock(),
    )


VALID_PARAMS = {
    "confidence_threshold": 0.25,
    "nms_threshold": 0.5,
    "track_threshold": 0.25,
    "match_threshold": 0.95,
    "track_buffer": 90,
    "max_center_distance": 400.0,
    "iou_threshold": 0.05,
}


# =============================================================================
# ONE CANONICAL ValidationError
# =============================================================================


def test_validation_error_has_a_single_definition() -> None:
    """``zebtrack.exceptions`` re-exports the class; it does not redefine it.

    Two same-named classes meant ``except`` on one silently missed the other.
    """
    assert public_exceptions.ValidationError is core_exceptions.ValidationError


def test_public_exceptions_module_re_exports_core() -> None:
    """Every name the public module exports is the core module's object."""
    for name in public_exceptions.__all__:
        assert getattr(public_exceptions, name) is getattr(core_exceptions, name), (
            f"{name} is a duplicate definition, not a re-export"
        )


# =============================================================================
# COORDINATOR ERRORS BELONG TO THE APPLICATION HIERARCHY
# =============================================================================


@pytest.mark.parametrize(
    "exc_class",
    [
        CoordinatorError,
        CoordinatorValidationError,
        CoordinatorDependencyError,
        DetectorSetupCoordinatorError,
    ],
)
def test_coordinator_errors_are_zebtrack_errors(exc_class: type[Exception]) -> None:
    """A UI boundary catching ZebTrackError must catch coordinator failures."""
    assert issubclass(exc_class, ZebTrackError)


def test_detector_setup_error_is_a_coordinator_error() -> None:
    """It was the one coordinator error deriving straight from Exception."""
    assert issubclass(DetectorSetupCoordinatorError, CoordinatorError)


def test_detector_setup_error_keeps_its_context() -> None:
    error = DetectorSetupCoordinatorError("boom", context={"params": {"a": 1}})

    assert error.context["params"] == {"a": 1}
    assert error.coordinator == "DetectorSetupCoordinator"


# =============================================================================
# THE TYPE SPLIT: user input vs. operational failure
# =============================================================================


def test_out_of_range_value_raises_validation_error(coordinator, detector_service) -> None:
    """The service's ValueError is a rejected user value, not a broken system."""
    detector_service.update_tracking_parameters.side_effect = ValueError(
        "conf_threshold must be between 0.0 and 1.0, got 1.5"
    )

    with pytest.raises(ValidationError) as exc_info:
        coordinator.update_detector_parameters({**VALID_PARAMS, "confidence_threshold": 1.5})

    assert "conf_threshold must be between 0.0 and 1.0" in str(exc_info.value)


def test_out_of_range_value_is_not_reported_as_an_operational_failure(
    coordinator, detector_service
) -> None:
    """Regression: it used to arrive as DetectorSetupCoordinatorError.

    That type carries an internal message, so a panel rendering ``str(exc)``
    would have shown the researcher "Parameter validation failed: ..." wrapped
    around a service-level string.
    """
    detector_service.update_tracking_parameters.side_effect = ValueError("track_buffer must be...")

    with pytest.raises(ValidationError) as exc_info:
        coordinator.update_detector_parameters(VALID_PARAMS)

    assert not isinstance(exc_info.value, DetectorSetupCoordinatorError)


def test_service_crash_stays_an_operational_failure(coordinator, detector_service) -> None:
    """A RuntimeError from the service is our bug, not the user's typo."""
    detector_service.update_tracking_parameters.side_effect = RuntimeError("plugin exploded")

    with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
        coordinator.update_detector_parameters(VALID_PARAMS)

    assert not isinstance(exc_info.value, ValidationError)
    assert "Failed to update detector parameters" in str(exc_info.value)


def test_unknown_scope_raises_validation_error(coordinator) -> None:
    with pytest.raises(ValidationError) as exc_info:
        coordinator.update_detector_parameters(VALID_PARAMS, scope="somewhere_else")

    assert "somewhere_else" in str(exc_info.value)


def test_validation_error_carries_the_rejected_input(coordinator, detector_service) -> None:
    """Details go to the log; the message goes to the dialog."""
    detector_service.update_tracking_parameters.side_effect = ValueError("out of range")

    with pytest.raises(ValidationError) as exc_info:
        coordinator.update_detector_parameters(VALID_PARAMS, scope="project")

    assert exc_info.value.details["scope"] == "project"
    assert exc_info.value.details["params"] == VALID_PARAMS


def test_successful_update_returns_true(coordinator) -> None:
    """The happy path is untouched by the exception split."""
    assert coordinator.update_detector_parameters(VALID_PARAMS) is True


# =============================================================================
# THE DEAD BOUNDARY IS GONE
# =============================================================================


def test_ui_state_controller_no_longer_declares_a_phantom_boundary() -> None:
    """``UIStateController.update_detector_parameters`` was never called.

    It wrapped the coordinator in ``except ValueError``, which the coordinator
    itself already consumed, so the handler could not fire even if something
    had called it. Leaving it in place made the flow look covered.
    """
    from zebtrack.coordinators.ui_state_coordinator import UIStateController

    assert not hasattr(UIStateController, "update_detector_parameters")
