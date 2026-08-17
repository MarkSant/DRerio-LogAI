"""Extended unit tests for core/services/detector_service.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.services.detector_service import DetectorService


class TestDetectorServiceExtended6:
    """Test DetectorService single subject tracker mode setting and detector status."""

    def test_set_single_subject_mode_with_detector(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )

        mock_detector = MagicMock()
        service.detector = mock_detector

        service.set_single_subject_mode(True)
        mock_detector.set_single_subject_mode.assert_called_once_with(True)

        service.set_single_subject_mode(False)
        mock_detector.set_single_subject_mode.assert_called_with(False)

    def test_set_single_subject_mode_no_detector(self):
        state_manager = MagicMock()
        project_manager = MagicMock()
        weight_manager = MagicMock()
        model_service = MagicMock()
        settings = MagicMock()

        service = DetectorService(
            state_manager=state_manager,
            project_manager=project_manager,
            weight_manager=weight_manager,
            model_service=model_service,
            settings_obj=settings,
        )
        service.detector = None
        # Should return safely
        service.set_single_subject_mode(True)
