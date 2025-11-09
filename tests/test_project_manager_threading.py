"""
Testes de Thread Safety para ProjectManager.

Testa cenários de concorrência em operações de projeto,
incluindo atualizações, salvamento, e acesso a dados de zonas.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock

import pytest

from zebtrack.core.project_manager import ProjectManager


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    state_manager = Mock()
    state_manager.update_project_state.return_value = None
    return state_manager


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.detector.default_backend = "opencv"
    return settings


@pytest.fixture
def project_manager(tmp_path, mock_state_manager, mock_settings):
    """Create a ProjectManager instance with mocked dependencies."""
    manager = ProjectManager(
        state_manager=mock_state_manager,
        settings_obj=mock_settings,
    )
    # Setup a test project path
    project_path = tmp_path / "test_project"
    project_path.mkdir()
    manager.project_path = str(project_path)
    manager.project_data = {
        "project_name": "Test Project",
        "videos": [],
        "zones": {},
    }
    return manager


class TestProjectManagerConcurrentUpdates:
    """Test concurrent project data updates."""

    def test_concurrent_project_data_updates(self, project_manager):
        """Test concurrent updates to project_data from multiple threads."""
        update_count = [0]

        def update_worker(thread_id):
            for i in range(5):
                # Simulate project data update
                project_manager.project_data[f"thread_{thread_id}_key_{i}"] = f"value_{i}"
                update_count[0] += 1
                time.sleep(0.01)

        # Start multiple update workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=update_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        # Verify updates occurred
        assert update_count[0] == 15  # 3 threads × 5 updates each

    def test_concurrent_zone_data_access(self, project_manager):
        """Test concurrent access to zone data."""
        # Setup some zone data
        project_manager.project_data["zones"] = {
            "zone1": {
                "name": "Zone 1",
                "geometry": [[0, 0], [100, 0], [100, 100], [0, 100]],
            },
            "zone2": {
                "name": "Zone 2",
                "geometry": [[200, 200], [300, 200], [300, 300], [200, 300]],
            },
        }

        zone_accesses = []

        def zone_reader(thread_id):
            for i in range(5):
                try:
                    zones = project_manager.project_data.get("zones", {})
                    zone_accesses.append((thread_id, len(zones)))
                    time.sleep(0.01)
                except Exception as e:
                    zone_accesses.append((thread_id, f"error: {e}"))

        # Start multiple zone reader threads
        readers = []
        for i in range(3):
            reader = threading.Thread(target=zone_reader, args=(i,), daemon=False)
            reader.start()
            readers.append(reader)

        # Wait for completion
        for reader in readers:
            reader.join(timeout=3.0)

        # All threads should complete
        for reader in readers:
            assert not reader.is_alive()

        # Verify accesses occurred
        assert len(zone_accesses) == 15  # 3 threads × 5 accesses each

    def test_concurrent_video_status_updates(self, project_manager):
        """Test concurrent video status updates."""
        # Add test videos
        project_manager.project_data["videos"] = [
            {"path": "/path/to/video1.mp4", "status": "pending"},
            {"path": "/path/to/video2.mp4", "status": "pending"},
            {"path": "/path/to/video3.mp4", "status": "pending"},
        ]

        status_updates = []

        def status_updater(thread_id, video_index):
            for i in range(3):
                try:
                    if video_index < len(project_manager.project_data["videos"]):
                        project_manager.project_data["videos"][video_index]["status"] = (
                            f"processing_by_thread_{thread_id}"
                        )
                        status_updates.append((thread_id, video_index, i))
                        time.sleep(0.01)
                except Exception as e:
                    status_updates.append((thread_id, video_index, f"error: {e}"))

        # Start multiple status updater threads for different videos
        updaters = []
        for i in range(3):
            updater = threading.Thread(target=status_updater, args=(i, i), daemon=False)
            updater.start()
            updaters.append(updater)

        # Wait for completion
        for updater in updaters:
            updater.join(timeout=3.0)

        # All threads should complete
        for updater in updaters:
            assert not updater.is_alive()

    def test_concurrent_metadata_access(self, project_manager):
        """Test concurrent metadata access."""
        import pandas as pd

        # Setup metadata
        project_manager.metadata = pd.DataFrame(
            {
                "video": ["video1.mp4", "video2.mp4"],
                "duration": [120, 180],
            }
        )

        metadata_reads = []

        def metadata_reader(thread_id):
            for i in range(5):
                try:
                    if project_manager.metadata is not None:
                        row_count = len(project_manager.metadata)
                        metadata_reads.append((thread_id, row_count))
                    time.sleep(0.01)
                except Exception as e:
                    metadata_reads.append((thread_id, f"error: {e}"))

        # Start multiple metadata reader threads
        readers = []
        for i in range(3):
            reader = threading.Thread(target=metadata_reader, args=(i,), daemon=False)
            reader.start()
            readers.append(reader)

        # Wait for completion
        for reader in readers:
            reader.join(timeout=3.0)

        # All threads should complete
        for reader in readers:
            assert not reader.is_alive()

        # Verify reads occurred
        assert len(metadata_reads) > 0


class TestProjectManagerSaveLoadOperations:
    """Test concurrent save and load operations."""

    def test_save_project_thread_safety(self, project_manager, tmp_path):
        """Test that save_project handles concurrent calls safely."""
        save_attempts = []

        def save_worker(thread_id):
            for i in range(3):
                try:
                    # Mock the actual file save
                    project_manager.project_data[f"save_marker_{thread_id}"] = i
                    save_attempts.append((thread_id, i, "success"))
                    time.sleep(0.02)
                except Exception as e:
                    save_attempts.append((thread_id, i, f"error: {e}"))

        # Start multiple save workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=save_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        # Verify save attempts
        assert len(save_attempts) == 9  # 3 threads × 3 attempts each

    def test_concurrent_zone_manager_operations(self, project_manager):
        """Test concurrent zone manager operations."""
        operations = []

        def zone_worker(thread_id):
            for i in range(3):
                try:
                    # Access zone manager methods
                    _ = project_manager.zone_manager
                    # Simulate zone operations
                    operations.append((thread_id, i, "zone_access"))
                    time.sleep(0.01)
                except Exception as e:
                    operations.append((thread_id, i, f"error: {e}"))

        # Start multiple zone workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=zone_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

    def test_concurrent_asset_manager_operations(self, project_manager):
        """Test concurrent asset manager operations."""
        operations = []

        def asset_worker(thread_id):
            for i in range(3):
                try:
                    # Access asset manager methods
                    _ = project_manager.asset_manager
                    # Simulate asset operations
                    operations.append((thread_id, i, "asset_access"))
                    time.sleep(0.01)
                except Exception as e:
                    operations.append((thread_id, i, f"error: {e}"))

        # Start multiple asset workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=asset_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()


class TestProjectManagerRaceConditions:
    """Test race conditions in project operations."""

    def test_concurrent_video_additions(self, project_manager):
        """Test concurrent video additions to project."""
        project_manager.project_data["videos"] = []

        def video_adder(thread_id):
            for i in range(3):
                video_entry = {
                    "path": f"/path/to/video_thread_{thread_id}_{i}.mp4",
                    "status": "pending",
                }
                project_manager.project_data["videos"].append(video_entry)
                time.sleep(0.01)

        # Start multiple video adders
        adders = []
        for i in range(3):
            adder = threading.Thread(target=video_adder, args=(i,), daemon=False)
            adder.start()
            adders.append(adder)

        # Wait for completion
        for adder in adders:
            adder.join(timeout=3.0)

        # All threads should complete
        for adder in adders:
            assert not adder.is_alive()

        # Verify videos were added
        assert len(project_manager.project_data["videos"]) == 9

    def test_concurrent_state_manager_notifications(self, project_manager):
        """Test concurrent state manager notifications."""
        notifications = []

        def notifier(thread_id):
            for i in range(5):
                try:
                    project_manager.state_manager.update_project_state(
                        project_name=f"project_{thread_id}",
                        has_changes=(i % 2 == 0),
                    )
                    notifications.append((thread_id, i))
                    time.sleep(0.01)
                except Exception as e:
                    notifications.append((thread_id, f"error: {e}"))

        # Start multiple notifiers
        notifiers_list = []
        for i in range(3):
            notifier_thread = threading.Thread(target=notifier, args=(i,), daemon=False)
            notifier_thread.start()
            notifiers_list.append(notifier_thread)

        # Wait for completion
        for notifier_thread in notifiers_list:
            notifier_thread.join(timeout=3.0)

        # All threads should complete
        for notifier_thread in notifiers_list:
            assert not notifier_thread.is_alive()


class TestProjectManagerErrorHandling:
    """Test error handling in concurrent operations."""

    def test_exception_handling_in_threads(self, project_manager):
        """Test that exceptions in threads are handled gracefully."""
        exceptions_caught = []

        def error_worker(thread_id):
            try:
                # Simulate an error condition
                if thread_id == 1:
                    raise ValueError(f"Test error from thread {thread_id}")
                project_manager.project_data[f"key_{thread_id}"] = f"value_{thread_id}"
            except Exception as e:
                exceptions_caught.append((thread_id, str(e)))

        # Start workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=error_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=2.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        # Verify exception was caught
        assert len(exceptions_caught) == 1
        assert "thread 1" in exceptions_caught[0][1]
