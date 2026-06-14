"""Mixin: video completion and output registration logic.

Extracted from VideoProcessingCoordinator (Etapa 2b).
Handles what happens after a video finishes processing:
- Detecting output trajectories (single and multi-aquarium)
- Registering outputs in ProjectManager
- Delegating report generation
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
    from zebtrack.coordinators.sequential_processing_coordinator import (
        SequentialProcessingCoordinator,
    )
    from zebtrack.core.project.project_manager import ProjectManager

log = structlog.get_logger()


class VideoCompletionMixin:
    """Mixin for video completion handling.

    Requires host class to provide:
    - self.project_manager
    - self._report_coordinator
    - self._sequential_coordinator
    - self._publish_event(event, payload)
    """

    # Declare host-provided attributes for mypy (set by coordinator __init__)
    project_manager: ProjectManager
    _report_coordinator: ReportGenerationCoordinator | None
    _sequential_coordinator: SequentialProcessingCoordinator | None

    # Host-provided methods (declared for mypy, implemented by host/other mixins)
    _publish_event: Any

    def _on_video_completed(self, videos_to_process, index, total, experiment_id, success) -> None:
        """Internal handler for single video completion."""
        log.info(
            "controller.video_completed",
            index=index,
            total=total,
            experiment_id=experiment_id,
            success=success,
        )
        if not success:
            return

        if 0 <= index < len(videos_to_process):
            video_info = videos_to_process[index]
            video_path = video_info.get("path")
            video_results_dir = video_info.get("results_dir")
            v_exp_id = video_info.get("experiment_id")
            if not v_exp_id and video_path:
                v_exp_id = os.path.splitext(os.path.basename(str(video_path)))[0]
            if not v_exp_id:
                v_exp_id = "Unknown"
        else:
            log.warning("controller.video_completed.index_out_of_bounds", index=index)
            return

        results_dir = video_results_dir or os.path.join(
            os.path.dirname(str(video_path)) if video_path else ".",
            f"{v_exp_id}_results",
        )

        trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{v_exp_id}.parquet")
        if not os.path.exists(trajectory_path):
            trajectory_path = os.path.join(results_dir, f"3_CoordMovimento_{experiment_id}.parquet")
        trajectory_exists = os.path.exists(trajectory_path)

        alt_multi_outputs: dict[int, dict] = {}

        # Exploded sequential task detection
        aq_id_override = video_info.get("aquarium_id")
        if aq_id_override is not None and trajectory_exists:
            log.info("controller.video_completed.exploded_task_detected", aq_id=aq_id_override)
            alt_multi_outputs[aq_id_override] = {
                "results_dir": results_dir,
                "parquet_files": {"trajectory": trajectory_path},
                "group": video_info.get("group") or (video_info.get("metadata", {}).get("group")),
                "subject_id": (
                    video_info.get("subject") or (video_info.get("metadata", {}).get("subject"))
                ),
                "day": video_info.get("day", 1),
            }
            trajectory_exists = False

        if (
            not trajectory_exists
            and not alt_multi_outputs
            and results_dir
            and os.path.exists(results_dir)
        ):
            for aq_id in [0, 1]:
                aq_subdir = os.path.join(results_dir, f"aquarium_{aq_id + 1}")
                if not os.path.exists(aq_subdir):
                    continue
                alt_paths = [
                    os.path.join(
                        aq_subdir, f"3_CoordMovimento_{v_exp_id}_aquarium_{aq_id + 1}.parquet"
                    ),
                    os.path.join(
                        aq_subdir,
                        f"3_CoordMovimento_{experiment_id}_aquarium_{aq_id + 1}.parquet",
                    ),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{v_exp_id}.parquet"),
                    os.path.join(aq_subdir, f"3_CoordMovimento_{experiment_id}.parquet"),
                ]
                for alt_p in alt_paths:
                    if os.path.exists(alt_p):
                        alt_multi_outputs[aq_id] = {
                            "results_dir": aq_subdir,
                            "parquet_files": {"trajectory": alt_p},
                            "group": (
                                video_info.get("group")
                                or (video_info.get("metadata", {}).get("group"))
                            ),
                            "subject_id": (
                                video_info.get("subject")
                                or (video_info.get("metadata", {}).get("subject"))
                            ),
                            "day": video_info.get("day", 1),
                        }
                        break
            if alt_multi_outputs:
                trajectory_exists = False

        if video_path:
            self.project_manager.update_video_status(video_path, "complete")

        self._register_completed_outputs(
            video_path or "",
            results_dir,
            trajectory_path,
            trajectory_exists,
            alt_multi_outputs,
            v_exp_id,
            video_results_dir,
        )

    def _register_completed_outputs(
        self,
        video_path: Path | str,
        results_dir: Path | str,
        trajectory_path: Path | str,
        trajectory_exists,
        alt_multi_outputs,
        experiment_id,
        video_results_dir: Path | str | None,
    ) -> None:
        """Register outputs after video completion."""
        outputs_by_aquarium = alt_multi_outputs.copy() if alt_multi_outputs else {}

        # Procura recursiva por saídas de cada aquário (layout antigo ``aquarium_N/``
        # OU novo por metadados ``Grupo_X/Dia_YY/Sujeito_Z/``) quando ainda não há
        # saídas detectadas e não há trajetória single. Cobre o paralelo multi-aquário.
        if not outputs_by_aquarium and not trajectory_exists:
            self._scan_multi_aquarium_outputs(results_dir, experiment_id, outputs_by_aquarium)
            if video_results_dir and str(video_results_dir) != str(results_dir):
                self._scan_multi_aquarium_outputs(
                    video_results_dir, experiment_id, outputs_by_aquarium
                )

        if trajectory_exists and not outputs_by_aquarium:
            self.project_manager.register_processing_outputs(
                video_path=str(video_path),
                results_dir=str(results_dir),
                trajectory_path=str(trajectory_path),
            )
            log.info(
                "controller.video_completed.trajectory_registered",
                experiment_id=experiment_id,
                trajectory_path=trajectory_path,
            )
        elif not trajectory_exists and not outputs_by_aquarium:
            log.warning(
                "controller.video_completed.trajectory_not_found",
                experiment_id=experiment_id,
                expected_path=trajectory_path,
            )

        if outputs_by_aquarium:
            self.project_manager.register_multi_aquarium_outputs(
                video_path=video_path,
                outputs_by_aquarium=cast(dict[int, dict], outputs_by_aquarium),
            )
            log.info(
                "controller.video_completed.multi_aquarium_registered",
                video=experiment_id,
                aquariums=list(outputs_by_aquarium.keys()),
            )
            # Delegate sequential advancement
            seq = self._sequential_coordinator
            if seq:
                seq._handle_sequential_multi_aquarium(video_path)
            self._publish_event(
                UIEvents.UI_REFRESH_PROJECT_VIEWS,
                payloads.ProjectViewsRefreshRequestedPayload(),
            )
            self._generate_completion_reports(video_path, experiment_id, True)
        elif trajectory_exists:
            self._generate_completion_reports(video_path, experiment_id, False)
            self._publish_event(
                UIEvents.UI_REFRESH_PROJECT_VIEWS,
                payloads.ProjectViewsRefreshRequestedPayload(),
            )

    @staticmethod
    def _scan_multi_aquarium_outputs(results_dir: Path | str, experiment_id, outputs_by_aquarium):
        """Scan ``results_dir`` recursively for per-aquarium trajectory parquets.

        Os arquivos de cada aquário podem estar em ``aquarium_{N}/`` (layout antigo)
        OU em ``Grupo_X/Dia_YY/Sujeito_Z/`` (layout por metadados). Procuramos em
        qualquer profundidade por ``3_CoordMovimento_*_aquarium_{N}.parquet`` e
        registramos cada aquário com a pasta-mãe como ``results_dir``. ``experiment_id``
        não é usado no casamento (o sufixo ``_aquarium_{N}`` basta), mantido por
        compatibilidade de assinatura.
        """
        del experiment_id  # não usado; casamento por ``_aquarium_{N}`` no nome
        if not results_dir or not os.path.exists(results_dir):
            return
        traj_pattern = re.compile(r"^3_CoordMovimento_.*_aquarium_(\d+)\.parquet$")
        for root, _dirs, files in os.walk(results_dir):
            for fname in files:
                match = traj_pattern.match(fname)
                if not match:
                    continue
                aq_id = int(match.group(1)) - 1
                if aq_id in outputs_by_aquarium:
                    continue  # primeiro match por aquário basta
                outputs_by_aquarium[aq_id] = {
                    "results_dir": root,
                    "parquet_files": {"trajectory": os.path.join(root, fname)},
                    "day": 1,
                }

    def _generate_completion_reports(self, video_path: Path | str, experiment_id, is_multi):
        """Generate reports after video completion."""
        rc = self._report_coordinator
        if not rc:
            log.warning(
                "controller.video_completed.report_coordinator_missing",
                video=experiment_id,
                is_multi=is_multi,
            )
            return
        try:
            rc.generate_project_reports([str(video_path)])
            log.info(
                "controller.video_completed.reports_generated",
                video=experiment_id,
                is_multi=is_multi,
            )
        except Exception as e:  # except Exception justified: report generation I/O + data
            log.error(
                f"controller.video_completed.report_failed_{'multi' if is_multi else 'single'}",
                video=experiment_id,
                error=str(e),
                exc_info=True,
            )
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Erro ao Gerar Relatórios",
                    message=f"Falha ao gerar relatórios para '{experiment_id}':\n{e}",
                ),
            )
