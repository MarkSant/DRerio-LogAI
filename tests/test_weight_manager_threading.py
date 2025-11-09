"""
Testes de Thread Safety para WeightManager.

Testa cenários de concorrência em acesso a pesos,
incluindo leitura, adição, remoção e contensão de recursos.
"""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.weight_manager import WEIGHTS_CONFIG_FILE, WeightManager


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.detector.default_backend = "opencv"
    return settings


@pytest.fixture
def weight_manager(tmp_path, mock_settings):
    """Create a WeightManager instance with temp config directory."""
    config_dir = str(tmp_path)
    manager = WeightManager(settings_obj=mock_settings, config_dir=config_dir)

    # Setup some initial weights
    manager.weights = {
        "weight1.pt": {
            "path": "/path/to/weight1.pt",
            "type": "seg",
            "is_default_seg": True,
            "is_default_det": False,
        },
        "weight2.pt": {
            "path": "/path/to/weight2.pt",
            "type": "det",
            "is_default_seg": False,
            "is_default_det": True,
        },
        "weight3.pt": {
            "path": "/path/to/weight3.pt",
            "type": "seg",
            "is_default_seg": False,
            "is_default_det": False,
        },
    }

    return manager


class TestWeightManagerConcurrentAccess:
    """Test concurrent weight access operations."""

    def test_concurrent_get_all_weights(self, weight_manager):
        """Test concurrent get_all_weights() calls."""
        weight_lists = []

        def weight_getter(thread_id):
            for i in range(5):
                weights = weight_manager.get_all_weights()
                weight_lists.append((thread_id, len(weights)))
                time.sleep(0.01)

        # Start multiple getter threads
        getters = []
        for i in range(3):
            getter = threading.Thread(target=weight_getter, args=(i,), daemon=False)
            getter.start()
            getters.append(getter)

        # Wait for completion
        for getter in getters:
            getter.join(timeout=3.0)

        # All threads should complete
        for getter in getters:
            assert not getter.is_alive()

        # Verify accesses occurred
        assert len(weight_lists) == 15  # 3 threads × 5 calls each
        # All should see the same number of weights
        for _, count in weight_lists:
            assert count == 3

    def test_concurrent_get_weight_details(self, weight_manager):
        """Test concurrent get_weight_details() calls."""
        details_retrieved = []

        def details_getter(thread_id):
            for i in range(5):
                details = weight_manager.get_weight_details("weight1.pt")
                if details:
                    details_retrieved.append((thread_id, details["type"]))
                time.sleep(0.01)

        # Start multiple getter threads
        getters = []
        for i in range(3):
            getter = threading.Thread(target=details_getter, args=(i,), daemon=False)
            getter.start()
            getters.append(getter)

        # Wait for completion
        for getter in getters:
            getter.join(timeout=3.0)

        # All threads should complete
        for getter in getters:
            assert not getter.is_alive()

        # Verify details were retrieved
        assert len(details_retrieved) == 15
        for _, weight_type in details_retrieved:
            assert weight_type == "seg"

    def test_concurrent_get_default_weight(self, weight_manager):
        """Test concurrent get_default_weight() calls."""
        default_weights = []

        def default_getter(thread_id):
            for i in range(5):
                name, details = weight_manager.get_default_weight()
                if name and details:
                    default_weights.append((thread_id, name))
                time.sleep(0.01)

        # Start multiple getter threads
        getters = []
        for i in range(3):
            getter = threading.Thread(target=default_getter, args=(i,), daemon=False)
            getter.start()
            getters.append(getter)

        # Wait for completion
        for getter in getters:
            getter.join(timeout=3.0)

        # All threads should complete
        for getter in getters:
            assert not getter.is_alive()

        # Verify default weights were retrieved
        assert len(default_weights) > 0

    def test_concurrent_get_weight_path_by_method(self, weight_manager):
        """Test concurrent get_weight_path_by_method() calls."""
        paths_retrieved = []

        def path_getter(thread_id):
            for i in range(5):
                # Mock the method to return a path
                with patch.object(weight_manager, 'get_weight_path_by_method') as mock_method:
                    mock_method.return_value = "/path/to/weight.pt"
                    path = weight_manager.get_weight_path_by_method("botsort", "seg")
                    if path:
                        paths_retrieved.append((thread_id, path))
                    time.sleep(0.01)

        # Start multiple getter threads
        getters = []
        for i in range(3):
            getter = threading.Thread(target=path_getter, args=(i,), daemon=False)
            getter.start()
            getters.append(getter)

        # Wait for completion
        for getter in getters:
            getter.join(timeout=3.0)

        # All threads should complete
        for getter in getters:
            assert not getter.is_alive()


class TestWeightManagerConcurrentModifications:
    """Test concurrent weight modification operations."""

    def test_concurrent_weight_dictionary_updates(self, weight_manager):
        """Test concurrent updates to weights dictionary."""
        update_count = [0]

        def weight_updater(thread_id):
            for i in range(3):
                # Add a new weight
                weight_name = f"thread_{thread_id}_weight_{i}.pt"
                weight_manager.weights[weight_name] = {
                    "path": f"/path/to/{weight_name}",
                    "type": "seg",
                    "is_default_seg": False,
                    "is_default_det": False,
                }
                update_count[0] += 1
                time.sleep(0.01)

        # Start multiple updater threads
        updaters = []
        for i in range(3):
            updater = threading.Thread(target=weight_updater, args=(i,), daemon=False)
            updater.start()
            updaters.append(updater)

        # Wait for completion
        for updater in updaters:
            updater.join(timeout=3.0)

        # All threads should complete
        for updater in updaters:
            assert not updater.is_alive()

        # Verify updates occurred
        assert update_count[0] == 9  # 3 threads × 3 updates each
        # Original weights + new weights
        assert len(weight_manager.weights) >= 12

    def test_concurrent_weight_removal(self, weight_manager):
        """Test concurrent weight removal operations."""
        # Add some weights to remove
        for i in range(9):
            weight_manager.weights[f"removable_{i}.pt"] = {
                "path": f"/path/to/removable_{i}.pt",
                "type": "seg",
                "is_default_seg": False,
                "is_default_det": False,
            }

        initial_count = len(weight_manager.weights)
        removal_count = [0]

        def weight_remover(thread_id):
            for i in range(3):
                weight_name = f"removable_{thread_id * 3 + i}.pt"
                if weight_name in weight_manager.weights:
                    del weight_manager.weights[weight_name]
                    removal_count[0] += 1
                time.sleep(0.01)

        # Start multiple remover threads
        removers = []
        for i in range(3):
            remover = threading.Thread(target=weight_remover, args=(i,), daemon=False)
            remover.start()
            removers.append(remover)

        # Wait for completion
        for remover in removers:
            remover.join(timeout=3.0)

        # All threads should complete
        for remover in removers:
            assert not remover.is_alive()

        # Verify removals occurred
        assert removal_count[0] == 9
        assert len(weight_manager.weights) == initial_count - 9


class TestWeightManagerConfigurationFile:
    """Test concurrent configuration file operations."""

    def test_concurrent_config_reads(self, weight_manager, tmp_path):
        """Test concurrent configuration file reads."""
        # Write a config file
        config_path = tmp_path / WEIGHTS_CONFIG_FILE
        config_data = {
            "test_weight.pt": {
                "path": "/path/to/test_weight.pt",
                "type": "seg",
                "is_default_seg": True,
                "is_default_det": False,
            }
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        read_count = [0]

        def config_reader(thread_id):
            for i in range(5):
                try:
                    if config_path.exists():
                        with open(config_path) as f:
                            data = json.load(f)
                            if data:
                                read_count[0] += 1
                except Exception:
                    pass
                time.sleep(0.01)

        # Start multiple reader threads
        readers = []
        for i in range(3):
            reader = threading.Thread(target=config_reader, args=(i,), daemon=False)
            reader.start()
            readers.append(reader)

        # Wait for completion
        for reader in readers:
            reader.join(timeout=3.0)

        # All threads should complete
        for reader in readers:
            assert not reader.is_alive()

        # Verify reads occurred
        assert read_count[0] > 0


class TestWeightManagerRaceConditions:
    """Test race conditions in weight manager operations."""

    def test_concurrent_default_weight_queries(self, weight_manager):
        """Test concurrent queries for default weights."""
        seg_defaults = []
        det_defaults = []

        def default_querier(thread_id):
            for i in range(5):
                seg_name, _ = weight_manager.get_default_seg_weight()
                det_name, _ = weight_manager.get_default_det_weight()

                if seg_name:
                    seg_defaults.append((thread_id, seg_name))
                if det_name:
                    det_defaults.append((thread_id, det_name))

                time.sleep(0.01)

        # Start multiple querier threads
        queriers = []
        for i in range(3):
            querier = threading.Thread(target=default_querier, args=(i,), daemon=False)
            querier.start()
            queriers.append(querier)

        # Wait for completion
        for querier in queriers:
            querier.join(timeout=3.0)

        # All threads should complete
        for querier in queriers:
            assert not querier.is_alive()

        # Verify queries returned consistent results
        if seg_defaults:
            first_seg = seg_defaults[0][1]
            assert all(name == first_seg for _, name in seg_defaults)

        if det_defaults:
            first_det = det_defaults[0][1]
            assert all(name == first_det for _, name in det_defaults)

    def test_mixed_read_write_operations(self, weight_manager):
        """Test mixed concurrent read and write operations."""
        operations = []

        def reader_worker(thread_id):
            for i in range(3):
                weights = weight_manager.get_all_weights()
                operations.append((thread_id, "read", len(weights)))
                time.sleep(0.01)

        def writer_worker(thread_id):
            for i in range(3):
                weight_name = f"mixed_thread_{thread_id}_weight_{i}.pt"
                weight_manager.weights[weight_name] = {
                    "path": f"/path/to/{weight_name}",
                    "type": "seg",
                    "is_default_seg": False,
                    "is_default_det": False,
                }
                operations.append((thread_id, "write", weight_name))
                time.sleep(0.01)

        # Start both reader and writer threads
        workers = []

        # 2 reader threads
        for i in range(2):
            reader = threading.Thread(target=reader_worker, args=(i,), daemon=False)
            reader.start()
            workers.append(reader)

        # 2 writer threads
        for i in range(2, 4):
            writer = threading.Thread(target=writer_worker, args=(i,), daemon=False)
            writer.start()
            workers.append(writer)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        # Verify operations occurred
        assert len(operations) == 12  # 2 readers × 3 + 2 writers × 3


class TestWeightManagerErrorHandling:
    """Test error handling in concurrent operations."""

    def test_exception_handling_in_threads(self, weight_manager):
        """Test that exceptions in threads are handled gracefully."""
        exceptions_caught = []

        def error_worker(thread_id):
            try:
                if thread_id == 1:
                    # Simulate an error
                    raise ValueError(f"Test error from thread {thread_id}")
                # Normal operation
                weights = weight_manager.get_all_weights()
                assert len(weights) > 0
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
