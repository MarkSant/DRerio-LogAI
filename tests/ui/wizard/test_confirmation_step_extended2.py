"""Extended unit tests for ui/wizard/confirmation_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep


class TestConfirmationStepExtended2:
    """Test ConfirmationStep summaries, step id, calibration, and custom regex formatting."""

    def test_append_custom_regex_info(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "custom_regex_patterns": {
                "group_pattern": r"Group_(\w+)",
                "day_pattern": r"Day_(\d+)",
                "subject_pattern": "",
            }
        }
        lines: list[str] = []
        step._append_custom_regex_info(lines)

        assert len(lines) > 0
        joined = "\n".join(lines)
        assert "Group_(\\w+)" in joined
        assert "Day_(\\d+)" in joined
        assert "—" in joined

    def test_append_detected_design(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "detected_design": {
                "groups": ["Control", "Treated"],
                "days": ["1", "2"],
                "confidence": 0.95,
            }
        }
        lines: list[str] = []
        step._append_detected_design(lines)

        assert len(lines) > 0
        joined = "\n".join(lines)
        assert "Control" in joined
        assert "Treated" in joined
        assert "95%" in joined

    def test_append_calibration(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "num_aquariums": 2,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 20.0,
            "aquarium_height_cm": 15.0,
        }
        lines: list[str] = []
        step._append_calibration(lines)

        joined = "\n".join(lines)
        assert "20.0 x 15.0 cm" in joined
        assert "Aquariums: 2" in joined or "Aquários: 2" in joined

    def test_append_detection_settings(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "model_selection": {"aquarium_method": "seg", "animal_method": "det"},
            "weight_assignments": {"aquarium": "best_seg.pt", "animal": "best_det.pt"},
            "use_openvino": True,
        }
        lines: list[str] = []
        step._append_detection_settings(lines)

        joined = "\n".join(lines)
        assert "best_seg.pt" in joined
        assert "best_det.pt" in joined
        assert "OpenVINO" in joined
