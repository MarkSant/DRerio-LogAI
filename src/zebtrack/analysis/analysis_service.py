# -*- coding: utf-8 -*-
"""
This module provides a unified service for performing comprehensive behavioral
and ROI-based analysis.
"""

from typing import Any, Dict, List, Tuple

import pandas as pd

from zebtrack.settings import settings
from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer


class AnalysisService:
    """
    A unified service layer that orchestrates behavioral and ROI analysis.
    This service acts as a single entry point for running a full analysis pipeline,
    making it easier to manage and extend.
    """

    def run_full_analysis(
        self,
        trajectory_df: pd.DataFrame,
        pixelcm_x: float,
        pixelcm_y: float,
        video_height_px: int,
        arena_polygon_px: List[tuple[float, float]],
        rois: List[ROI],
        fps: float,
        # Analysis-specific parameters
        freezing_vel_threshold: float,
        freezing_min_duration: float,
    ) -> Tuple[Dict[str, Any], ConcreteBehavioralAnalyzer, ROIAnalyzer]:
        """
        Runs a complete analysis pipeline on the given trajectory data.

        This method instantiates the necessary analyzers, runs all relevant
        metric calculations, and compiles them into a single, structured report.

        Args:
            trajectory_df: Raw trajectory data.
            pixelcm_x: Pixels-to-cm conversion factor for the x-axis.
            pixelcm_y: Pixels-to-cm conversion factor for the y-axis.
            video_height_px: Height of the video in pixels.
            arena_polygon_px: Vertices of the arena in pixels.
            rois: A list of ROI objects for analysis.
            fps: Frames per second of the video.
            freezing_vel_threshold: Velocity threshold for detecting freezing.
            freezing_min_duration: Minimum duration for a freezing episode.

        Returns:
            A tuple containing:
            - A nested dictionary with the full analysis report.
            - The instance of ConcreteBehavioralAnalyzer used.
            - The instance of ROIAnalyzer used.
        """
        # 1. Initialize the core behavioral analyzer
        b_analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=trajectory_df.copy(),  # Use a copy to prevent side effects
            pixelcm_x=pixelcm_x,
            pixelcm_y=pixelcm_y,
            video_height_px=video_height_px,
            arena_polygon_px=arena_polygon_px,
            fps=fps,
        )

        # 2. Initialize the behavioral report
        report = {
            "comportamento_geral": {
                "distancia_total_cm": b_analyzer.calculate_total_distance(),
                "estatisticas_velocidade": b_analyzer.get_velocity_stats(),
                "episodios_congelamento": b_analyzer.detect_freezing_episodes(
                    vel_threshold=freezing_vel_threshold,
                    min_duration=freezing_min_duration,
                ),
                "tortuosidade": b_analyzer.get_tortuosity(),
                "curvas_acentuadas": b_analyzer.calculate_sharp_turns(
                    90.0
                ),  # Assuming 90 as default
            }
        }

        # 3. If ROIs are provided, perform ROI analysis and append to the report
        if not rois:
            return report, b_analyzer, None

        r_analyzer = ROIAnalyzer(
            behavior_analyzer=b_analyzer,
            rois=rois,
            inclusion_rule=settings.roi_inclusion_rule,
            buffer_radius_value=settings.roi_buffer_radius_value,
            min_bbox_overlap_ratio=settings.roi_min_bbox_overlap_ratio,
        )
        report["analise_roi"] = {
            "tempo_gasto_por_roi": r_analyzer.get_time_spent_in_rois(),
            "latencia_primeira_entrada": r_analyzer.get_latency_to_first_entry(),
            "contagem_entradas": r_analyzer.get_entry_counts(),
            "contagem_saidas": r_analyzer.get_exit_counts(),
            "distancia_por_roi": r_analyzer.get_distance_in_rois(),
            "estatisticas_velocidade_por_roi": (
                r_analyzer.get_velocity_stats_in_rois()
            ),
            "congelamento_por_roi": r_analyzer.get_freezing_in_rois(
                vel_threshold=freezing_vel_threshold,
                min_duration=freezing_min_duration,
            ),
            "transicoes_entre_rois": r_analyzer.get_roi_transitions().to_dict("index"),
        }
        report["log_eventos"] = r_analyzer.get_event_log().to_dict("records")

        return report, b_analyzer, r_analyzer
