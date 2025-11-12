"""Test settings injection in UI components."""

from zebtrack.ui.components.validation_manager import ValidationManager
from zebtrack.ui.components.widget_factory import WidgetFactory


class MockGUI:
    """Mock GUI object for testing."""

    def __init__(self, settings_obj=None):
        self.settings = settings_obj

    def show_error(self, title, message):
        """Mock error display."""
        pass

    def show_info(self, title, message):
        """Mock info display."""
        pass

    def _extract_setting(self, obj, path, default):
        """Mock setting extraction."""
        result = obj
        for key in path:
            if hasattr(result, key):
                result = getattr(result, key)
            else:
                return default
        return result

    def _deep_merge_dicts(self, base, override):
        """Mock deep merge."""
        import copy

        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        return result


def test_validation_manager_requires_settings(test_settings):
    """ValidationManager stores injected settings_obj parameter."""
    gui = MockGUI()

    # Should work with settings
    manager = ValidationManager(gui, settings_obj=test_settings)
    assert manager._settings is test_settings


def test_validation_manager_uses_injected_settings(test_settings):
    """ValidationManager uses injected settings, not singleton."""
    import copy

    # Create two separate settings instances using deepcopy
    settings1 = copy.deepcopy(test_settings)
    settings1.video_processing.fps = 25

    settings2 = copy.deepcopy(test_settings)
    settings2.video_processing.fps = 60

    gui1 = MockGUI()
    gui2 = MockGUI()

    manager1 = ValidationManager(gui1, settings_obj=settings1)
    manager2 = ValidationManager(gui2, settings_obj=settings2)

    assert manager1._settings.video_processing.fps == 25
    assert manager2._settings.video_processing.fps == 60


def test_validation_manager_handles_none_settings():
    """ValidationManager handles None settings gracefully."""
    gui = MockGUI()
    manager = ValidationManager(gui, settings_obj=None)

    assert manager._settings is None


def test_widget_factory_requires_settings(test_settings):
    """WidgetFactory stores injected settings_obj parameter."""
    gui = MockGUI()

    # Should work with settings
    factory = WidgetFactory(gui, settings_obj=test_settings)
    assert factory._settings is test_settings


def test_widget_factory_uses_injected_settings(test_settings):
    """WidgetFactory uses injected settings, not singleton."""
    import copy

    settings1 = copy.deepcopy(test_settings)
    settings1.video_processing.fps = 25

    settings2 = copy.deepcopy(test_settings)
    settings2.video_processing.fps = 60

    gui1 = MockGUI()
    gui2 = MockGUI()

    factory1 = WidgetFactory(gui1, settings_obj=settings1)
    factory2 = WidgetFactory(gui2, settings_obj=settings2)

    assert factory1._settings.video_processing.fps == 25
    assert factory2._settings.video_processing.fps == 60


def test_widget_factory_handles_none_settings():
    """WidgetFactory handles None settings gracefully."""
    gui = MockGUI()
    factory = WidgetFactory(gui, settings_obj=None)

    assert factory._settings is None


def test_validation_manager_isolation(test_settings):
    """Multiple ValidationManager instances maintain separate settings."""
    import copy

    settings1 = copy.deepcopy(test_settings)
    settings1.trajectory_smoothing.window_length = 5

    settings2 = copy.deepcopy(test_settings)
    settings2.trajectory_smoothing.window_length = 9

    gui1 = MockGUI()
    gui2 = MockGUI()

    manager1 = ValidationManager(gui1, settings_obj=settings1)
    manager2 = ValidationManager(gui2, settings_obj=settings2)

    # Verify isolation - changing one doesn't affect the other
    assert manager1._settings.trajectory_smoothing.window_length == 5
    assert manager2._settings.trajectory_smoothing.window_length == 9

    # Modify one
    manager1._settings.trajectory_smoothing.window_length = 7

    # Verify the other is unaffected
    assert manager1._settings.trajectory_smoothing.window_length == 7
    assert manager2._settings.trajectory_smoothing.window_length == 9


def test_widget_factory_isolation(test_settings):
    """Multiple WidgetFactory instances maintain separate settings."""
    import copy

    settings1 = copy.deepcopy(test_settings)
    settings1.recorder.flush_interval_seconds = 5.0

    settings2 = copy.deepcopy(test_settings)
    settings2.recorder.flush_interval_seconds = 10.0

    gui1 = MockGUI()
    gui2 = MockGUI()

    factory1 = WidgetFactory(gui1, settings_obj=settings1)
    factory2 = WidgetFactory(gui2, settings_obj=settings2)

    # Verify isolation
    assert factory1._settings.recorder.flush_interval_seconds == 5.0
    assert factory2._settings.recorder.flush_interval_seconds == 10.0

    # Modify one
    factory1._settings.recorder.flush_interval_seconds = 3.0

    # Verify the other is unaffected
    assert factory1._settings.recorder.flush_interval_seconds == 3.0
    assert factory2._settings.recorder.flush_interval_seconds == 10.0
