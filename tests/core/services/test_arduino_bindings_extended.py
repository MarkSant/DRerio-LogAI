"""
Extended unit tests for Arduino bindings configuration models.
"""

from __future__ import annotations

from zebtrack.core.services.arduino_bindings import (
    ArduinoBinding,
    ArduinoBindingConfig,
    TokenConflict,
)


class TestArduinoBindingsExtended:
    """Test ArduinoBinding and ArduinoBindingConfig behaviors."""

    def test_token_conflict_describe(self):
        conflict = TokenConflict(
            token=5,
            enter_rois=["ZoneA"],
            exit_rois=["ZoneB"],
        )
        description = conflict.describe()
        assert "5" in description
        assert "ZoneA" in description
        assert "ZoneB" in description

    def test_arduino_binding_label_normalization_and_display_name(self):
        b1 = ArduinoBinding(roi="ZoneA", on_enter=1, on_exit=2, label="Choque")
        assert b1.roi == "ZoneA"
        assert b1.label == "Choque"
        assert b1.display_name() == "Choque"

        b2 = ArduinoBinding(roi="ZoneB", on_enter=3, label="   ")
        assert b2.label is None
        assert b2.display_name() == "ZoneB"

    def test_arduino_binding_config_from_project_data(self):
        # Empty project data
        assert ArduinoBindingConfig.from_project_data({}).is_empty() is True

        # Unexpected shape
        empty_cfg = ArduinoBindingConfig.from_project_data({"arduino_bindings": "not_a_list"})
        assert empty_cfg.is_empty() is True

        # List with valid and malformed entries
        raw = [
            {"roi": "Zone1", "on_enter": 1, "on_exit": 2},
            "not a dict",
            {"roi": "Zone2", "on_enter": 3, "on_exit": 4},
        ]
        cfg = ArduinoBindingConfig.from_project_data({"arduino_bindings": raw})
        assert len(cfg.bindings) == 2
        assert cfg.roi_names() == ["Zone1", "Zone2"]
        assert cfg.session_end_tokens() == [2, 4]

    def test_arduino_binding_config_storage_and_conflicts(self):
        cfg = ArduinoBindingConfig(
            bindings=[
                ArduinoBinding(roi="Zone1", on_enter=1, on_exit=2),
                # Token 2 is enter on Zone2 and exit on Zone1
                ArduinoBinding(roi="Zone2", on_enter=2, on_exit=3),
            ]
        )

        storage = cfg.to_storage()
        assert len(storage) == 2
        assert storage[0]["roi"] == "Zone1"
        assert storage[0]["on_enter"] == 1

        conflicts = cfg.token_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].token == 2
        assert conflicts[0].enter_rois == ["Zone2"]
        assert conflicts[0].exit_rois == ["Zone1"]
