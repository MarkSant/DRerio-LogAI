"""
Extended unit tests for ModelOverrideService.

Tests copying settings to external project paths, resolution with slot weights,
error handling during config loading/saving, and event emissions.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.core.services.model_override_service import ModelOverrideService


class TestModelOverrideServiceExtended:
    """Test extended ModelOverrideService behaviors."""

    def _build_service(
        self,
        *,
        project_path: str | None = None,
        project_data: dict[str, Any] | None = None,
        event_bus: Any = None,
    ) -> tuple[ModelOverrideService, MagicMock, MagicMock, MagicMock]:
        pm = MagicMock()
        pm.project_path = project_path
        pm.project_data = project_data or {}
        pws = MagicMock()
        sm = MagicMock()

        service = ModelOverrideService(
            state_manager=cast(Any, sm),
            project_manager=cast(Any, pm),
            project_workflow_service=cast(Any, pws),
            settings_obj=cast(Any, SimpleNamespace()),
            event_bus=event_bus,
        )
        return service, pm, pws, sm

    def test_copy_global_model_settings_to_project_path_matches_current_project(
        self, tmp_path: Path
    ):
        service, pm, pws, _ = self._build_service(project_path=str(tmp_path))
        service.copy_global_model_settings_to_project = MagicMock(return_value=("weight.pt", True))  # type: ignore[method-assign]

        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(tmp_path),
            get_global_defaults=lambda: {"use_openvino": True},
            get_active_weight_name=lambda: "weight.pt",
        )
        assert res == ("weight.pt", True)
        service.copy_global_model_settings_to_project.assert_called_once()

    def test_copy_global_model_settings_to_project_path_missing_config(self, tmp_path: Path):
        service, _, _, _ = self._build_service(project_path=str(tmp_path / "other"))
        empty_dir = tmp_path / "empty_proj"
        empty_dir.mkdir()

        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(empty_dir),
            get_global_defaults=lambda: {},
            get_active_weight_name=lambda: None,
        )
        assert res is None

    def test_copy_global_model_settings_to_project_path_no_project_service(self, tmp_path: Path):
        service, pm, pws, _ = self._build_service(project_path="/different/path")
        pm.project_service = None

        target_dir = tmp_path / "ext_proj"
        target_dir.mkdir()
        (target_dir / "project_config.json").write_text("{}", encoding="utf-8")

        pws.get_global_project_slot_weights.return_value = {"seg:zebrafish": "best.pt"}

        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(target_dir),
            get_global_defaults=lambda: {"use_openvino": True},
            get_active_weight_name=lambda: "best.pt",
        )
        assert res is None

    def test_copy_global_model_settings_to_project_path_load_and_save_failures(
        self, tmp_path: Path
    ):
        service, pm, pws, _ = self._build_service(project_path="/different/path")
        project_service = MagicMock()
        pm.project_service = project_service

        target_dir = tmp_path / "ext_proj"
        target_dir.mkdir()
        (target_dir / "project_config.json").write_text("{}", encoding="utf-8")

        # Load fails
        project_service.load_project_config.side_effect = RuntimeError("Read error")
        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(target_dir),
            get_global_defaults=lambda: {},
            get_active_weight_name=lambda: None,
        )
        assert res is None

        # Save fails
        project_service.load_project_config.side_effect = None
        project_service.load_project_config.return_value = {}
        project_service.save_project_config.side_effect = OSError("Disk full")

        pws.get_global_project_slot_weights.return_value = {}
        pws._get_legacy_animal_slot_key.return_value = "seg:zebrafish"
        pws._normalize_slot_weights.return_value = {"seg:zebrafish": "best.pt"}

        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(target_dir),
            get_global_defaults=lambda: {"active_weight": "best.pt", "use_openvino": False},
            get_active_weight_name=lambda: "best.pt",
        )
        assert res is None

    def test_copy_global_model_settings_to_project_path_success(self, tmp_path: Path):
        mock_event_bus = MagicMock()
        service, pm, pws, _ = self._build_service(
            project_path="/different/path",
            event_bus=mock_event_bus,
        )
        project_service = MagicMock()
        pm.project_service = project_service

        target_dir = tmp_path / "ext_proj"
        target_dir.mkdir()
        (target_dir / "project_config.json").write_text("{}", encoding="utf-8")

        project_service.load_project_config.return_value = {}
        pws.get_global_project_slot_weights.return_value = {"seg:zebrafish": "custom.pt"}
        pws._normalize_slot_weights.return_value = {"seg:zebrafish": "custom.pt"}
        pws._get_legacy_animal_slot_key.return_value = "seg:zebrafish"

        res = service.copy_global_model_settings_to_project_path(
            target_dir=str(target_dir),
            get_global_defaults=lambda: {"use_openvino": True},
            get_active_weight_name=lambda: "custom.pt",
        )
        assert res == ("custom.pt", True)
        project_service.save_project_config.assert_called_once()
        mock_event_bus.publish.assert_called_once()
