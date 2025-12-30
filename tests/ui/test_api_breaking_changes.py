import inspect
import json
from pathlib import Path

import pytest

from zebtrack.ui.gui import ApplicationGUI


def load_baseline():
    path = Path(__file__).parent.parent / "fixtures/api_baseline.json"
    with open(path) as f:
        return json.load(f)


def get_current_signature(method_name):
    if not hasattr(ApplicationGUI, method_name):
        return None
    method = getattr(ApplicationGUI, method_name)
    sig = inspect.signature(method)
    params = []
    for name, param in sig.parameters.items():
        param_data = {
            "name": name,
            "kind": str(param.kind),
            "default": str(param.default) if param.default != inspect.Parameter.empty else None,
            "annotation": str(param.annotation)
            if param.annotation != inspect.Parameter.empty
            else None,
        }
        params.append(param_data)
    return params


class TestAPIBreakingChanges:
    """
    Tests to detect breaking changes in the public API.

    Task 3.2: Create Tests for Validating API Breaking Changes.
    """

    @pytest.fixture(scope="class")
    def baseline(self):
        return load_baseline()

    def test_public_methods_exist(self, baseline):
        """Ensure no tracked public methods were removed."""
        for method_name in baseline:
            assert hasattr(ApplicationGUI, method_name), (
                f"Method {method_name} was removed from ApplicationGUI!"
            )

    def test_signatures_match(self, baseline):
        """Ensure signatures match the baseline exactly."""
        for method_name, expected_params in baseline.items():
            if not hasattr(ApplicationGUI, method_name):
                continue  # Handled by test_public_methods_exist

            current_params = get_current_signature(method_name)

            # Compare length
            assert len(current_params) == len(expected_params), (
                f"Signature length mismatch for {method_name}: "
                f"expected {len(expected_params)}, got {len(current_params)}"
            )

            # Compare each parameter
            for i, (exp, curr) in enumerate(zip(expected_params, current_params, strict=False)):
                assert exp["name"] == curr["name"], (
                    f"Param name mismatch in {method_name} at index {i}: "
                    f"expected {exp['name']}, got {curr['name']}"
                )
                assert exp["kind"] == curr["kind"], (
                    f"Param kind mismatch in {method_name} for {exp['name']}"
                )

                # Check defaults
                assert exp["default"] == curr["default"], (
                    f"Default value changed in {method_name} for {exp['name']}: "
                    f"expected {exp['default']}, got {curr['default']}"
                )
