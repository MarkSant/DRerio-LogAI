"""
Tests for ProjectOverviewWidget component.
"""

import pytest

from zebtrack.ui.components.project_overview import ProjectOverviewWidget
from zebtrack.ui.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create an event bus instance."""
    return EventBus()


@pytest.fixture
def overview_widget(tkinter_root, event_bus):
    """Create a ProjectOverviewWidget instance for testing."""
    widget = ProjectOverviewWidget(tkinter_root, event_bus=event_bus)
    widget.pack()
    tkinter_root.update()
    return widget


def test_widget_initialization(overview_widget):
    """Test that widget initializes correctly."""
    assert overview_widget.project_overview_tree is not None
    assert overview_widget.status_cards_frame is not None
    assert overview_widget.project_status_vars is not None
    assert isinstance(overview_widget.project_status_vars, dict)


def test_status_vars_initialized(overview_widget):
    """Test that status variables are initialized with default values."""
    assert "total" in overview_widget.project_status_vars
    assert "pending" in overview_widget.project_status_vars
    assert "processing" in overview_widget.project_status_vars
    assert "processed" in overview_widget.project_status_vars
    assert "complete" in overview_widget.project_status_vars
    assert "failed" in overview_widget.project_status_vars

    # Check default values
    for key in ["total", "pending", "processing", "processed", "complete", "failed"]:
        assert overview_widget.project_status_vars[key].get() == "0"


def test_update_status_counts(overview_widget):
    """Test that update_status_counts updates the status variables."""
    test_counts = {
        "total": 10,
        "pending": 3,
        "processing": 2,
        "processed": 3,
        "complete": 1,
        "failed": 1,
    }

    overview_widget.update_status_counts(test_counts)

    assert overview_widget.project_status_vars["total"].get() == "10"
    assert overview_widget.project_status_vars["pending"].get() == "3"
    assert overview_widget.project_status_vars["processing"].get() == "2"
    assert overview_widget.project_status_vars["processed"].get() == "3"
    assert overview_widget.project_status_vars["complete"].get() == "1"
    assert overview_widget.project_status_vars["failed"].get() == "1"


def test_clear_tree(overview_widget):
    """Test that clear_tree removes all items from the tree."""
    # Add some test items
    overview_widget.add_tree_item("test1", "Test Item 1", values=("Status 1", "Data 1"))
    overview_widget.add_tree_item("test2", "Test Item 2", values=("Status 2", "Data 2"))

    # Verify items were added
    assert len(overview_widget.project_overview_tree.get_children()) == 2

    # Clear the tree
    overview_widget.clear_tree()

    # Verify tree is empty
    assert len(overview_widget.project_overview_tree.get_children()) == 0


def test_add_tree_item(overview_widget):
    """Test that add_tree_item adds items correctly."""
    overview_widget.add_tree_item(
        "item1",
        "Test Item",
        values=("Status", "Data")
    )

    children = overview_widget.project_overview_tree.get_children()
    assert len(children) == 1
    assert children[0] == "item1"

    item_text = overview_widget.project_overview_tree.item(children[0], "text")
    assert item_text == "Test Item"

    item_values = overview_widget.project_overview_tree.item(children[0], "values")
    assert item_values == ("Status", "Data")


def test_add_tree_item_with_parent(overview_widget):
    """Test that add_tree_item can add child items."""
    # Add parent
    overview_widget.add_tree_item("parent", "Parent Item", values=("P Status", "P Data"))

    # Add child
    overview_widget.add_tree_item(
        "child",
        "Child Item",
        parent="parent",
        values=("C Status", "C Data")
    )

    # Verify parent-child relationship
    parent_children = overview_widget.project_overview_tree.get_children("parent")
    assert len(parent_children) == 1
    assert parent_children[0] == "child"


def test_expand_and_collapse_tree_item(overview_widget):
    """Test expand and collapse functionality."""
    # Add parent and child
    overview_widget.add_tree_item("parent", "Parent", values=("", ""))
    overview_widget.add_tree_item("child", "Child", parent="parent", values=("", ""))

    # Test expand
    overview_widget.expand_tree_item("parent")
    is_open = overview_widget.project_overview_tree.item("parent", "open")
    assert is_open == 1 or is_open is True  # Tk returns 1 or True depending on version

    # Test collapse
    overview_widget.collapse_tree_item("parent")
    is_open = overview_widget.project_overview_tree.item("parent", "open")
    assert is_open == 0 or is_open is False  # Tk returns 0 or False depending on version


def test_event_emission_on_refresh(overview_widget, event_bus):
    """Test that clicking refresh emits the correct event."""
    events_received = []

    def handler(data):
        events_received.append(("project.refresh_requested", data))

    # Subscribe to the widget's event bus (not the fixture event bus)
    overview_widget.event_bus.subscribe("project.refresh_requested", handler)

    # Trigger refresh (simulate button click)
    overview_widget._on_refresh_clicked()

    # Process the event queue manually (since there's no background worker in tests)
    from zebtrack.ui.event_bus import EventType
    events = overview_widget.event_bus.drain(max_items=10)
    for event in events:
        if event.type == EventType.NAMED:
            overview_widget.event_bus.dispatch_named_event(event.payload)

    assert len(events_received) == 1, f"Expected 1 event but got {len(events_received)}"
    assert events_received[0][0] == "project.refresh_requested"


def test_tree_has_correct_columns(overview_widget):
    """Test that tree has the correct columns configured."""
    tree = overview_widget.project_overview_tree

    # Check columns
    columns = tree["columns"]
    assert "status" in columns
    assert "metadata" in columns

    # Check headings
    assert tree.heading("#0")["text"] == "Vídeos"
    assert tree.heading("status")["text"] == "Status"
    assert tree.heading("metadata")["text"] == "Metadados"


def test_multiple_status_updates(overview_widget):
    """Test that multiple consecutive status updates work correctly."""
    # First update
    overview_widget.update_status_counts({"total": 5, "pending": 5})
    assert overview_widget.project_status_vars["total"].get() == "5"
    assert overview_widget.project_status_vars["pending"].get() == "5"

    # Second update
    overview_widget.update_status_counts({"total": 10, "pending": 3, "complete": 7})
    assert overview_widget.project_status_vars["total"].get() == "10"
    assert overview_widget.project_status_vars["pending"].get() == "3"
    assert overview_widget.project_status_vars["complete"].get() == "7"

    # Third update (partial)
    overview_widget.update_status_counts({"processing": 2})
    assert overview_widget.project_status_vars["processing"].get() == "2"
    # Previous values should remain unchanged
    assert overview_widget.project_status_vars["total"].get() == "10"


def test_complex_tree_hierarchy(overview_widget):
    """Test building a complex tree hierarchy."""
    # Group 1
    overview_widget.add_tree_item("group1", "🏷️ Group 1", values=("10 videos", ""))
    overview_widget.add_tree_item("day1", "📅 Day 1", parent="group1", values=("5 videos", ""))
    overview_widget.add_tree_item("video1", "🐟 Subject 1", parent="day1", values=("✅", "Arena ROI"))

    # Group 2
    overview_widget.add_tree_item("group2", "🏷️ Group 2", values=("5 videos", ""))
    overview_widget.add_tree_item("day2", "📅 Day 1", parent="group2", values=("5 videos", ""))
    overview_widget.add_tree_item("video2", "🐟 Subject 1", parent="day2", values=("⏳", ""))

    # Verify structure
    root_children = overview_widget.project_overview_tree.get_children()
    assert len(root_children) == 2

    group1_children = overview_widget.project_overview_tree.get_children("group1")
    assert len(group1_children) == 1

    day1_children = overview_widget.project_overview_tree.get_children("day1")
    assert len(day1_children) == 1


@pytest.mark.parametrize("status_key,expected_value", [
    ("total", "0"),
    ("pending", "0"),
    ("processing", "0"),
    ("processed", "0"),
    ("complete", "0"),
    ("failed", "0"),
])
def test_initial_status_values(overview_widget, status_key, expected_value):
    """Test that all status variables have correct initial values."""
    assert overview_widget.project_status_vars[status_key].get() == expected_value


def test_populate_tree_with_hierarchy(overview_widget):
    """Test populate_tree_with_hierarchy method."""
    hierarchy_data = {
        'groups': [
            {
                'id': 'group1',
                'display': 'Group 1',
                'status_summary': '5 videos',
                'data_summary': 'Arena 3/5',
                'days': [
                    {
                        'id': 'day1',
                        'title': 'Day 1',
                        'status': 'Complete',
                        'data': 'Arena ROI',
                        'videos': [
                            {
                                'id': 'video1',
                                'display_name': 'Subject 1',
                                'status': 'Complete',
                                'data_badges': '✓',
                                'path': '/path/to/video1.mp4'
                            }
                        ]
                    }
                ]
            }
        ]
    }
    video_index = {'/path/to/video1.mp4': {'status': 'complete'}}

    overview_widget.populate_tree_with_hierarchy(hierarchy_data, video_index)

    # Verify tree was populated
    root_children = overview_widget.project_overview_tree.get_children()
    assert len(root_children) == 1  # One group

    # Verify group has children (days)
    group_children = overview_widget.project_overview_tree.get_children(root_children[0])
    assert len(group_children) == 1  # One day

    # Verify day has children (videos)
    day_children = overview_widget.project_overview_tree.get_children(group_children[0])
    assert len(day_children) == 1  # One video


def test_populate_tree_with_empty_hierarchy(overview_widget):
    """Test populate_tree_with_hierarchy with empty data."""
    hierarchy_data = {'groups': []}
    video_index = {}

    overview_widget.populate_tree_with_hierarchy(hierarchy_data, video_index)

    # Verify tree is empty
    root_children = overview_widget.project_overview_tree.get_children()
    assert len(root_children) == 0
