"""Core business logic and application services.

This package contains the main ViewModel, coordinators, services, managers,
and detector implementations, organized into domain-specific sub-packages:

Sub-packages
------------
``detection``
    AI detection, tracking, zone scaling, calibration, and aquarium detection.
    Key exports: ``Detector``, ``SingleDetector``, ``MultiAquariumDetector``,
    ``ZoneData``, ``AquariumData``, ``MultiAquariumZoneData``, ``Calibration``,
    ``ZoneScaler``, ``DetectionPostProcessor``.

``project``
    Project data management — project lifecycle, zones, assets, video catalog,
    ROI templates, parquet I/O, and metadata.
    Key exports: ``ProjectManager``, ``ProjectService``, ``ZoneManager``,
    ``VideoManager``, ``AssetType``, ``ROITemplateSchema``.

``video``
    Video processing pipeline — processing workers, mode definitions,
    video classification/selection/validation/metadata services.
    Key exports: ``ProcessingMode``, ``ProcessingReport``,
    ``VideoProcessingService``.

``recording``
    Recording and live camera workflows — recording service, live camera
    service/mode, Arduino facade.
    Key exports: ``RecordingService``, ``LiveCameraService``, ``LiveCameraMode``.

``services``
    Domain services — detector service, model service, weight manager,
    wizard service, zone management facade.
    Key exports: ``DetectorService``, ``ModelService``, ``WeightManager``,
    ``WizardService``.

Root modules (infrastructure)
-----------------------------
- ``state_manager`` — Centralized observable state management
- ``exceptions`` — Domain exception hierarchy
- ``ui_scheduler`` — Thread-safe UI scheduling
- ``dependency_container`` — DI container (MainViewModelDependencies)
- ``main_view_model`` — Top-level application orchestrator
- ``application_bootstrapper`` — Service initialization

Phase 4.10 — Sub-packetize core/ into domain-specific sub-packages.
"""
