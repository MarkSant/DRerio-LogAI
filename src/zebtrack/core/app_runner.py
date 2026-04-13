"""Application startup orchestration for ZebTrack-AI."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import warnings
from collections.abc import Callable
from typing import Any, Literal, cast

import structlog

from zebtrack.constants import SPLASH_CLOSE_DELAY_MS
from zebtrack.logging_config import configure_logging

# Suppress pkg_resources deprecation from docxcompose (setuptools pinned to <81)
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated",
    category=UserWarning,
    module="docxcompose.properties",
)


def run_app(
    *,
    tk_module: Any,
    messagebox_module: Any,
    configure_logging_fn: Any | None = None,
) -> None:
    """Run the application startup sequence."""
    parser = argparse.ArgumentParser(description="ZebTrack-AI: Multi-animal tracking.")
    parser.add_argument(
        "--log-level",
        action="append",
        help="Override log level: MODULE=LEVEL (e.g., zebtrack.core.detector=DEBUG)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset benchmark cache and local config, then exit.",
    )
    args = parser.parse_args()

    if args.reset:
        _perform_reset()
        sys.exit(0)

    if configure_logging_fn is None:
        configure_logging_fn = configure_logging

    configure_logging_levels = _setup_logging(args.log_level, configure_logging_fn)
    log = structlog.get_logger()

    from zebtrack.settings import load_settings

    settings_obj = _load_settings_or_exit(
        load_settings=load_settings,
        configure_logging_levels=configure_logging_levels,
        tk_module=tk_module,
        messagebox_module=messagebox_module,
        log=log,
    )

    from zebtrack.utils import set_seed

    if settings_obj.reproducibility and settings_obj.reproducibility.seed:
        set_seed(settings_obj.reproducibility.seed)
        log.info("reproducibility.seed.set", seed=settings_obj.reproducibility.seed)

    log.info("application.starting", component="main")
    _set_windows_app_id(log)

    from zebtrack.core.dependency_container import LazyRef
    from zebtrack.core.di_registrations import (
        ContainerContext,
        build_container,
        resolve_main_view_model,
    )
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.settings import save_settings
    from zebtrack.ui.event_bus_v2 import EventBusV2
    from zebtrack.ui.window_utils import maximize_window

    try:
        root = tk_module.Tk()
        root.withdraw()

        from zebtrack.ui.icon_utils import set_window_icon
        from zebtrack.ui.splash_screen import create_splash

        set_window_icon(root)
        splash = create_splash(parent=root)
        splash.update_progress(0.0, "Carregando configurações...")

        # Detect first launch (no cached benchmark) and inform user
        _detect_first_launch(settings_obj, splash)

        _run_benchmark_if_enabled(settings_obj, splash, save_settings, log)

        event_bus = EventBusV2()
        state_manager = StateManager(enable_history=True, max_history_size=100)
        ui_coordinator = UIScheduler(root=root, event_bus=event_bus)
        recorder_factory = RecorderFactory(settings_obj=settings_obj)
        cancel_event = threading.Event()
        controller_ref: LazyRef = LazyRef("MainViewModel")

        context = ContainerContext(
            root=root,
            settings_obj=settings_obj,
            event_bus=event_bus,
            state_manager=state_manager,
            ui_coordinator=ui_coordinator,
            recorder_factory=recorder_factory,
            cancel_event=cancel_event,
            controller_ref=controller_ref,
        )
        container = build_container(context)

        _warm_container(container, splash)

        controller = resolve_main_view_model(container)
        controller.bind_events()

        splash.update_progress(1.0, "Pronto!")
        root.update()

        def close_splash_and_show_main() -> None:
            splash.destroy()
            maximize_window(root)
            root.deiconify()

        root.after(SPLASH_CLOSE_DELAY_MS, close_splash_and_show_main)
        controller.run()

    except Exception:
        log.critical("unhandled.exception", exc_info=True)
        splash_obj = locals().get("splash")
        root_obj = locals().get("root")
        _handle_fatal_error(messagebox_module, log, root=root_obj, splash=splash_obj)
    finally:
        log.info("application.finished", component="main")


def _perform_reset() -> None:
    """Delete benchmark cache and local config to restore defaults."""
    from pathlib import Path

    targets = [
        Path("openvino_model_cache") / "system_benchmark.json",
        Path("config.local.yaml"),
    ]
    for path in targets:
        if path.exists():
            path.unlink()
            print(f"Removed: {path}")
        else:
            print(f"Not found (skip): {path}")
    print("Reset complete. Restart the application to apply defaults.")


def _setup_logging(
    overrides: list[str] | None,
    configure_logging_fn: Callable[[], None],
) -> Callable[[Any | None], None]:
    configure_logging_fn()

    from zebtrack.logging_config import configure_logging_levels

    configure_logging_levels()
    _apply_log_level_overrides(overrides)
    return configure_logging_levels


def _apply_log_level_overrides(overrides: list[str] | None) -> None:
    if not overrides:
        return

    for override in overrides:
        try:
            module, level = override.split("=", 1)
            level_upper = level.upper()
            if level_upper not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                print(f"Warning: Invalid log level '{level}' in override. Ignoring.")
                continue

            logging.getLogger(module).setLevel(level_upper)
            print(f"CLI override: Set log level for '{module}' to '{level_upper}'")
        except ValueError:
            print(f"Warning: Invalid --log-level format '{override}'. Use MODULE=LEVEL.")


def _load_settings_or_exit(
    *,
    load_settings: Callable[[], Any],
    configure_logging_levels: Callable[[Any | None], None],
    tk_module: Any,
    messagebox_module: Any,
    log: Any,
) -> Any:
    try:
        settings_obj = load_settings()
        log.info(
            "settings.loaded",
            camera_index=settings_obj.camera.index,
            yolo_path=settings_obj.yolo_model.path,
        )
        configure_logging_levels(settings_obj)
        return settings_obj
    except FileNotFoundError as e:
        log.critical("settings.load.file_not_found", error=str(e))
        root = tk_module.Tk()
        root.withdraw()
        messagebox_module.showerror(
            "Configuration File Not Found",
            f"Could not find configuration file: {e}\n\n"
            "The application requires 'config.yaml' to start.",
        )
        sys.exit(1)
    except ValueError as e:
        log.critical("settings.load.validation_error", error=str(e))
        root = tk_module.Tk()
        root.withdraw()
        messagebox_module.showerror(
            "Configuration Validation Error",
            f"Configuration file contains invalid values:\n\n{e}\n\n"
            "Please check your config.yaml file.",
        )
        sys.exit(1)


def _set_windows_app_id(log: Any) -> None:
    if os.name != "nt":
        return

    try:
        import ctypes

        myappid = "zebtrack.ai.app.v1"
        windll = getattr(ctypes, "windll", None)
        if windll is not None:
            cast(Any, windll).shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        log.debug("main.app_user_model_id.suppressed", exc_info=True)


def _detect_first_launch(settings_obj: Any, splash: Any) -> None:
    """Detect first launch and inform the splash screen."""
    if not settings_obj.openvino.auto_benchmark:
        return
    try:
        from zebtrack.utils.hardware_benchmark import load_cached_benchmark

        is_first = load_cached_benchmark() is None
        splash.set_first_launch(is_first)
    except Exception:
        structlog.get_logger().debug("app.detect_first_launch.suppressed", exc_info=True)


def _run_benchmark_if_enabled(
    settings_obj: Any,
    splash: Any,
    save_settings: Callable[[Any], None],
    log: Any,
) -> None:
    if not settings_obj.openvino.auto_benchmark:
        return

    try:
        from zebtrack.utils.hardware_benchmark import (
            get_or_run_benchmark,
            load_cached_benchmark,
        )

        cached = load_cached_benchmark()
        if cached is None:
            splash.update_progress(0.02, "Otimizando para seu hardware (primeira execução)...")
            log.info("benchmark.running_first_time")

            def progress_cb(step: int, total: int, message: str) -> None:
                # Benchmark occupies progress range 0.02-0.15
                frac = 0.02 + (step / max(total, 1)) * 0.13
                splash.update_progress(frac, message)

            benchmark_result = get_or_run_benchmark(
                quick_mode=True,
                progress_callback=progress_cb,
            )

            if benchmark_result.recommendation:
                rec = benchmark_result.recommendation

                if rec.backend == "openvino":
                    settings_obj.model_selection.use_openvino = True
                    settings_obj.openvino.device = cast(
                        Literal["AUTO", "CPU", "GPU", "NPU"], rec.device_live
                    )
                    settings_obj.openvino.device_batch = cast(
                        Literal["AUTO", "CPU", "GPU", "NPU"], rec.device_batch
                    )
                    settings_obj.openvino.performance_hint_live = cast(
                        Literal["LATENCY", "THROUGHPUT"], rec.openvino_hint_live
                    )
                    settings_obj.openvino.performance_hint_batch = cast(
                        Literal["LATENCY", "THROUGHPUT"], rec.openvino_hint_batch
                    )
                    settings_obj.openvino.precision = cast(
                        Literal["FP32", "FP16", "INT8"], rec.openvino_precision
                    )
                    settings_obj.openvino.enable_model_cache = rec.enable_model_cache

                # Apply memory mode recommendation
                settings_obj.performance.memory_mode = cast(
                    Literal["normal", "low"], rec.recommended_memory_mode
                )

                # Apply adaptive inference size if enabled
                if settings_obj.performance.auto_inference_size:
                    if rec.recommended_inference_size != 640:
                        settings_obj.yolo_model.inference_size = rec.recommended_inference_size
                        log.info(
                            "benchmark.inference_size_adapted",
                            size=rec.recommended_inference_size,
                        )

                # Apply low-memory overrides
                if rec.recommended_memory_mode == "low":
                    settings_obj.openvino.batch_nireq = 1
                    settings_obj.performance.enable_parallel_analysis = False
                    log.info("benchmark.low_memory_mode_applied")

                try:
                    save_settings(settings_obj)
                    log.info("benchmark.settings_persisted")
                except Exception as e:
                    log.warning("benchmark.settings_persist_failed", error=str(e))

                log.info(
                    "benchmark.applied_recommendations",
                    backend=rec.backend,
                    device_live=rec.device_live,
                    estimated_fps=round(rec.estimated_fps_live, 1),
                )
        else:
            log.info(
                "benchmark.using_cached",
                device=cached.recommendation.device_live if cached.recommendation else "unknown",
            )
    except Exception as e:
        log.warning("benchmark.failed", error=str(e))


def _warm_container(container: Any, splash: Any) -> None:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.services.model_service import ModelService
    from zebtrack.core.video.video_processing_service import VideoProcessingService
    from zebtrack.ui.gui import ApplicationGUI

    # Phase weights: (cumulative fraction, message)
    # Benchmark phase occupies 0.0-0.15, warm-up occupies 0.15-0.95
    phases = [
        (0.20, "Carregando sistema de modelos..."),
        (0.35, "Inicializando gerenciador de projetos..."),
        (0.50, "Configurando detector..."),
        (0.65, "Preparando processamento de vídeo..."),
        (0.85, "Criando interface gráfica..."),
        (0.95, "Finalizando inicialização..."),
    ]

    splash.update_progress(phases[0][0], phases[0][1])
    container.resolve(ModelService)
    splash.update_progress(phases[1][0], phases[1][1])
    container.resolve(ProjectManager)
    container.resolve(ProjectWorkflowService)
    splash.update_progress(phases[2][0], phases[2][1])
    container.resolve(DetectorService)
    splash.update_progress(phases[3][0], phases[3][1])
    container.resolve(VideoProcessingService)
    splash.update_progress(phases[4][0], phases[4][1])
    container.resolve(ApplicationGUI)
    splash.update_progress(phases[5][0], phases[5][1])


def _handle_fatal_error(
    messagebox_module: Any,
    log: Any,
    *,
    root: Any | None,
    splash: Any | None,
) -> None:
    try:
        if splash is not None:
            splash.destroy()
    except Exception:
        log.debug("main.splash_destroy.suppressed", exc_info=True)

    try:
        if root is not None:
            root.deiconify()
    except Exception:
        log.debug("main.root_deiconify.suppressed", exc_info=True)

    try:
        from zebtrack.logging_config import resolve_log_path

        log_path = resolve_log_path("analysis.log")
    except Exception:
        log.debug("main.resolve_log_path.fallback", exc_info=True)
        log_path = "analysis.log"

    messagebox_module.showerror(
        "Fatal Error",
        f"A fatal error occurred. See {log_path} for details.",
    )
