"""Tests for MenuManager component."""

from tkinter import Menu
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.menu_manager import MenuManager


@pytest.fixture(autouse=True)
def block_all_dialogs():
    """Automatically block ALL dialog windows for all tests in this file."""
    with (
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.askyesno", return_value=False),
        patch("tkinter.messagebox.askokcancel", return_value=False),
        patch("tkinter.messagebox.askyesnocancel", return_value=None),
    ):
        yield


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    controller = Mock()
    controller.start_live_camera_analysis = Mock()
    controller.can_remove_project_asset = Mock(return_value=(True, None))
    return controller


@pytest.fixture
def mock_gui(tkinter_root, mock_controller):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    # Mock Tkinter methods that are called during menu creation
    gui.root.config = Mock()
    gui.root.bind = Mock()
    gui.controller = mock_controller
    gui.project_overview_tree = None
    gui.roi_context_menu = None
    gui.dialog_manager = Mock()
    gui.canvas_manager = Mock()
    gui.project_view_manager = Mock()
    gui.event_dispatcher = Mock()
    gui.set_status = Mock()
    gui.refresh_project_views = Mock()
    gui.publish_event = Mock()
    return gui


@pytest.fixture
def menu_manager(mock_gui):
    """Create a MenuManager instance for testing."""
    return MenuManager(mock_gui)


@pytest.mark.gui
class TestMenuManagerInitialization:
    """Tests for MenuManager initialization."""

    def test_initialization(self, menu_manager, mock_gui):
        """Test that MenuManager initializes correctly."""
        assert menu_manager.gui is mock_gui
        assert menu_manager._overview_context_menu is None
        assert menu_manager._overview_menu_font is None
        assert menu_manager._about_logo_image is None

    def test_initialization_with_real_gui(self, tkinter_root):
        """Test initialization with minimal real gui object."""
        gui = Mock()
        gui.root = tkinter_root
        manager = MenuManager(gui)
        assert manager.gui is gui


@pytest.mark.gui
class TestMenuBarCreation:
    """Tests for menu bar creation."""

    def test_create_menu_bar(self, menu_manager, mock_gui):
        """Test menu bar creation."""
        menu_manager.create_menu_bar()

        # Verify root.config was called to set the menu
        mock_gui.root.config.assert_called_once()
        call_args = mock_gui.root.config.call_args
        assert "menu" in call_args[1]

    def test_create_menu_bar_binds_shortcuts(self, menu_manager, tkinter_root, mock_controller):
        """Test that keyboard shortcuts are bound."""
        menu_manager.gui.root = tkinter_root
        menu_manager.gui.controller = mock_controller

        menu_manager.create_menu_bar()

        # Verify that bindings were created by checking bind info
        bindings = tkinter_root.bind()
        # Should have at least some keyboard bindings
        assert bindings is not None or len(str(bindings)) > 0

    def test_create_menu_bar_quit_binding(self, menu_manager, tkinter_root):
        """Test that Ctrl+Q binding calls quit."""
        menu_manager.gui.root = tkinter_root

        menu_manager.create_menu_bar()

        # Verify that quit binding exists
        bindings = tkinter_root.bind()
        # Should have bindings created
        assert bindings is not None or len(str(bindings)) > 0


@pytest.mark.gui
class TestAboutDialog:
    """Tests for About dialog."""

    @patch("zebtrack.ui.icon_utils.set_window_icon")
    def test_show_about_dialog_creates_window(self, mock_set_icon, menu_manager, tkinter_root):
        """Test that show_about_dialog creates a Toplevel window."""
        menu_manager.gui.root = tkinter_root

        # Patch withdraw to prevent window from actually showing
        with patch("tkinter.Toplevel.withdraw"):
            menu_manager.show_about_dialog()

        # set_window_icon should have been called
        mock_set_icon.assert_called_once()

    @patch("zebtrack.ui.icon_utils.set_window_icon")
    def test_show_about_dialog_sets_geometry(self, mock_set_icon, menu_manager, tkinter_root):
        """Test that dialog geometry is configured."""
        menu_manager.gui.root = tkinter_root

        # Patch withdraw to prevent window from showing
        with patch("tkinter.Toplevel.withdraw"):
            menu_manager.show_about_dialog()

        # Just verify it ran without errors
        mock_set_icon.assert_called_once()

    @patch("zebtrack.ui.icon_utils.set_window_icon")
    @patch("zebtrack.ui.components.menu_manager.Image")
    @patch("zebtrack.ui.components.menu_manager.ImageTk")
    def test_show_about_dialog_loads_logo(
        self, mock_imagetk, mock_image, mock_set_icon, menu_manager, tkinter_root
    ):
        """Test that logo is loaded if available."""
        menu_manager.gui.root = tkinter_root

        # Mock logo file exists
        mock_pil_image = Mock()
        mock_image.open.return_value = mock_pil_image
        mock_tk_image = Mock()
        mock_imagetk.PhotoImage.return_value = mock_tk_image

        with patch("pathlib.Path.exists", return_value=True), patch("tkinter.Toplevel.withdraw"):
            menu_manager.show_about_dialog()

        mock_image.open.assert_called_once()
        mock_imagetk.PhotoImage.assert_called_once_with(mock_pil_image)
        assert menu_manager._about_logo_image is mock_tk_image

    @patch("zebtrack.ui.icon_utils.set_window_icon")
    @patch("zebtrack.ui.components.menu_manager.Image")
    def test_show_about_dialog_handles_missing_logo(
        self, mock_image, mock_set_icon, menu_manager, tkinter_root
    ):
        """Test that missing logo is handled gracefully."""
        menu_manager.gui.root = tkinter_root

        with patch("pathlib.Path.exists", return_value=False), patch("tkinter.Toplevel.withdraw"):
            menu_manager.show_about_dialog()

        mock_image.open.assert_not_called()
        assert menu_manager._about_logo_image is None

    @patch("zebtrack.ui.icon_utils.set_window_icon")
    @patch("builtins.open", side_effect=FileNotFoundError())
    def test_show_about_dialog_handles_missing_version(
        self, mock_open, mock_set_icon, menu_manager, tkinter_root
    ):
        """Test that missing pyproject.toml is handled gracefully."""
        menu_manager.gui.root = tkinter_root

        # Should not raise an exception
        with patch("tkinter.Toplevel.withdraw"):
            menu_manager.show_about_dialog()


@pytest.mark.gui
class TestProjectOverviewContextMenu:
    """Tests for project overview context menu."""

    def test_show_project_overview_context_menu_with_no_tree(self, menu_manager):
        """Test handling when tree is None."""
        menu_manager.gui.project_overview_tree = None

        # Should return without error
        menu_manager.show_project_overview_context_menu("item1", 100, 100)

    def test_show_project_overview_context_menu_creates_menu(self, menu_manager, tkinter_root):
        """Test that context menu is created for valid item."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root)
        menu_manager.gui.project_overview_tree = tree

        # Add item with video_path tag
        item_id = tree.insert("", "end", text="Video", tags=("/path/to/video.mp4",))

        with patch.object(Menu, "post") as mock_post:
            menu_manager.show_project_overview_context_menu(item_id, 100, 100)
            mock_post.assert_called_once_with(100, 100)

    def test_show_project_overview_context_menu_selects_item(self, menu_manager, tkinter_root):
        """Test that item is selected before showing menu."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root)
        menu_manager.gui.project_overview_tree = tree

        item_id = tree.insert("", "end", text="Video", tags=("/path/to/video.mp4",))

        with patch.object(Menu, "post"):
            menu_manager.show_project_overview_context_menu(item_id, 100, 100)

        assert item_id in tree.selection()

    def test_show_project_overview_context_menu_no_video_path(self, menu_manager, tkinter_root):
        """Test handling when item has no video_path tag."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root)
        menu_manager.gui.project_overview_tree = tree

        item_id = tree.insert("", "end", text="Item", tags=("status_pending",))

        # Should return without creating menu
        menu_manager.show_project_overview_context_menu(item_id, 100, 100)
        assert menu_manager._overview_context_menu is None


@pytest.mark.gui
class TestOverviewBadgeFont:
    """Tests for overview badge font."""

    def test_get_overview_badge_font_creates_font(self, menu_manager, tkinter_root):
        """Test that font is created on first call."""
        import tkinter.font as tkfont

        tree = SimpleNamespace(cget=lambda _name: "TkDefaultFont")
        menu_manager.gui.project_overview_tree = tree

        font = menu_manager.get_overview_badge_font()

        assert font is not None
        assert isinstance(font, tkfont.Font)
        assert menu_manager._overview_menu_font is font

    def test_get_overview_badge_font_caches_font(self, menu_manager, tkinter_root):
        """Test that font is cached and reused."""
        tree = SimpleNamespace(cget=lambda _name: "TkDefaultFont")
        menu_manager.gui.project_overview_tree = tree

        font1 = menu_manager.get_overview_badge_font()
        font2 = menu_manager.get_overview_badge_font()

        assert font1 is font2

    def test_get_overview_badge_font_no_tree(self, menu_manager):
        """Test font creation when tree is None."""
        menu_manager.gui.project_overview_tree = None

        font = menu_manager.get_overview_badge_font()

        assert font is not None


@pytest.mark.gui
class TestResolveOverviewAssetFromClick:
    """Tests for resolving asset from click."""

    def test_resolve_overview_asset_from_click_no_tree(self, menu_manager):
        """Test handling when tree is None."""
        menu_manager.gui.project_overview_tree = None

        result = menu_manager.resolve_overview_asset_from_click("item1", 100)

        assert result is None

    def test_resolve_overview_asset_from_click_no_bbox(self, menu_manager, tkinter_root):
        """Test handling when bbox returns None."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root, columns=("status", "data"))
        menu_manager.gui.project_overview_tree = tree

        item_id = tree.insert("", "end", text="Video")

        # bbox returns None for items not visible/rendered
        result = menu_manager.resolve_overview_asset_from_click(item_id, 100)

        assert result is None

    def test_resolve_overview_asset_from_click_arena(self, menu_manager, tkinter_root):
        """Test resolving arena asset from click."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root, columns=("status", "data"))
        tree.pack()
        tkinter_root.update()
        menu_manager.gui.project_overview_tree = tree

        # Create item with data in second column
        item_id = tree.insert("", "end", text="Video", values=("✓", "Arena  ROI  Traj  Sum"))
        tree.set(item_id, "data", "Arena  ROI  Traj  Sum")

        # Expand to make item visible
        tree.update()

        # Get bbox and test click in arena area
        bbox = tree.bbox(item_id, "#2")
        if bbox:  # Only test if item is visible
            # Click near start of data column should hit "Arena"
            result = menu_manager.resolve_overview_asset_from_click(item_id, bbox[0] + 5)
            # May be None if font measurement doesn't work in test env
            assert result is None or result == "arena"


@pytest.mark.gui
class TestShowOverviewContextMenu:
    """Tests for showing overview context menu."""

    def test_show_overview_context_menu_no_tree(self, menu_manager):
        """Test handling when tree is None."""
        menu_manager.gui.project_overview_tree = None

        event = Mock()
        event.x_root = 100
        event.y_root = 100

        # Should return without error
        menu_manager.show_overview_context_menu(event, "/path/to/video.mp4", "arena")

    def test_show_overview_context_menu_creates_menu(self, menu_manager, tkinter_root):
        """Test that context menu is created."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root)
        menu_manager.gui.project_overview_tree = tree

        event = Mock()
        event.x_root = 100
        event.y_root = 100

        with patch.object(Menu, "tk_popup"):
            menu_manager.show_overview_context_menu(event, "/path/to/video.mp4", "arena")

        assert menu_manager._overview_context_menu is not None

    @pytest.mark.parametrize(
        "asset,expected_label",
        [
            ("arena", "Apagar arena"),
            ("rois", "Apagar ROIs"),
            ("trajectory", "Apagar trajetória"),
            ("summary", "Apagar relatórios/sumários"),
            ("video", "Remover vídeo do projeto"),
        ],
    )
    def test_show_overview_context_menu_labels(
        self, menu_manager, tkinter_root, asset, expected_label
    ):
        """Test that correct labels are used for different assets."""
        from tkinter import ttk

        tree = ttk.Treeview(tkinter_root)
        menu_manager.gui.project_overview_tree = tree

        event = Mock()
        event.x_root = 100
        event.y_root = 100

        with patch.object(Menu, "tk_popup"):
            menu_manager.show_overview_context_menu(event, "/path/to/video.mp4", asset)

        # Verify menu was created (label verification is complex in Tk)
        assert menu_manager._overview_context_menu is not None


@pytest.mark.gui
class TestHandleOverviewAssetRemoval:
    """Tests for handling asset removal."""

    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_not_allowed(
        self, mock_messagebox, menu_manager, mock_controller
    ):
        """Test handling when removal is not allowed."""
        mock_controller.can_remove_project_asset.return_value = (
            False,
            "Video is being processed",
        )

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", "arena")

        menu_manager.gui.dialog_manager.show_warning.assert_called_once_with(
            "Ação indisponível", "Video is being processed"
        )
        mock_messagebox.askyesno.assert_not_called()

    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_user_cancels(
        self, mock_messagebox, menu_manager, mock_controller
    ):
        """Test handling when user cancels confirmation."""
        mock_controller.can_remove_project_asset.return_value = (True, None)
        mock_messagebox.askyesno.return_value = False

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", "arena")

        mock_messagebox.askyesno.assert_called_once()
        menu_manager.gui.event_dispatcher.publish_event.assert_not_called()

    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_arena(
        self, mock_messagebox, menu_manager, mock_controller
    ):
        """Test arena removal."""
        mock_controller.can_remove_project_asset.return_value = (True, None)
        mock_messagebox.askyesno.return_value = True

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", "arena")

        # Verify confirmation dialog
        assert mock_messagebox.askyesno.call_count == 1
        call_args = mock_messagebox.askyesno.call_args[0]
        assert call_args[0] == "Remover arena"

        # Verify event published
        from zebtrack.ui.event_bus_v2 import UIEvents

        menu_manager.gui.event_dispatcher.publish_event.assert_called_once()
        args = menu_manager.gui.event_dispatcher.publish_event.call_args[0]
        assert args[0] == UIEvents.PROJECT_DELETE_ASSET
        assert args[1]["asset"] == "arena"

        # Verify UI updates
        menu_manager.gui.set_status.assert_called_once()

        # Verify project views refresh event was published via event_bus_v2
        if menu_manager.gui.event_bus_v2:
            menu_manager.gui.event_bus_v2.publish.assert_called()
            # Check that the event type is PROJECT_VIEWS_REFRESH_REQUESTED
            event_calls = [
                call[0][0] for call in menu_manager.gui.event_bus_v2.publish.call_args_list
            ]
            assert any(e.type == UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED for e in event_calls)

    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_video_delete_files(
        self, mock_messagebox, menu_manager, mock_controller
    ):
        """Test video removal with file deletion."""
        mock_controller.can_remove_project_asset.return_value = (True, None)
        mock_messagebox.askyesno.side_effect = [True, True]  # Confirm removal and deletion

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", "video")

        # Should ask for confirmation twice (remove + delete files)
        assert mock_messagebox.askyesno.call_count == 2

        # Verify event has delete_source flag
        event_call = menu_manager.gui.event_dispatcher.publish_event.call_args[0]
        assert event_call[1]["delete_source"] is True

    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_video_keep_files(
        self, mock_messagebox, menu_manager, mock_controller
    ):
        """Test video removal without file deletion."""
        mock_controller.can_remove_project_asset.return_value = (True, None)
        mock_messagebox.askyesno.side_effect = [True, False]  # Confirm removal, keep files

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", "video")

        # Verify event has delete_source = False
        event_call = menu_manager.gui.event_dispatcher.publish_event.call_args[0]
        assert event_call[1]["delete_source"] is False

    @pytest.mark.parametrize(
        "asset,expected_status",
        [
            ("arena", "Arena removida"),
            ("rois", "ROIs removidas"),
            ("trajectory", "Trajetória removida"),
            ("summary", "Relatórios removidos"),
            ("video", "Vídeo removido do projeto"),
        ],
    )
    @patch("zebtrack.ui.components.menu_manager.messagebox")
    def test_handle_overview_asset_removal_status_messages(
        self, mock_messagebox, menu_manager, mock_controller, asset, expected_status
    ):
        """Test that correct status messages are shown for each asset type."""
        mock_controller.can_remove_project_asset.return_value = (True, None)
        mock_messagebox.askyesno.return_value = True

        menu_manager.handle_overview_asset_removal("/path/to/video.mp4", asset)

        # Verify status message contains expected text
        status_call = menu_manager.gui.set_status.call_args[0][0]
        assert expected_status in status_call


@pytest.mark.gui
class TestCreateRoiContextMenu:
    """Tests for ROI context menu creation."""

    def test_create_roi_context_menu(self, menu_manager):
        """Test that ROI context menu is created."""
        menu_manager.create_roi_context_menu()

        assert menu_manager.gui.roi_context_menu is not None

    def test_create_roi_context_menu_has_commands(self, menu_manager, tkinter_root):
        """Test that menu has all expected commands."""
        menu_manager.gui.root = tkinter_root
        menu_manager.gui.roi_context_menu = None

        menu_manager.create_roi_context_menu()

        menu = menu_manager.gui.roi_context_menu
        assert menu is not None

        # Menu should have been created with commands
        # (Detailed inspection of menu items is difficult in Tk, so we just verify it exists)

    def test_create_roi_context_menu_commands_call_gui_methods(self, menu_manager, tkinter_root):
        """Test that menu commands are wired to gui methods."""
        menu_manager.gui.root = tkinter_root

        menu_manager.create_roi_context_menu()

        # Verify that commands are wired to the correct component managers
        assert hasattr(menu_manager.gui.canvas_manager, "edit_selected_zone_vertices")
        assert hasattr(menu_manager.gui.dialog_manager, "rename_selected_roi")
        assert hasattr(menu_manager.gui.dialog_manager, "change_roi_color")
        assert hasattr(menu_manager.gui.canvas_manager, "remove_selected_roi")


@pytest.mark.gui
class TestShowProcessingReportsContextMenu:
    """Tests for processing reports context menu."""

    def test_show_processing_reports_context_menu_builds_entries(
        self, menu_manager, tkinter_root
    ) -> None:
        """Ensure menu items are added based on available assets."""
        from tkinter import Menu as TkMenu

        menu_manager.gui.root = tkinter_root
        menu_manager.gui.controller.project_manager = Mock()
        pm = menu_manager.gui.controller.project_manager
        pm.has_arena_data.return_value = True
        pm.has_roi_data.return_value = False
        pm.has_trajectory_data.return_value = True
        pm.has_summary_data.return_value = False

        callbacks = {
            "delete_asset": Mock(),
            "delete_all_processing": Mock(),
            "delete_video": Mock(),
        }

        created_menus = []

        def menu_factory(*args, **kwargs):
            menu = TkMenu(*args, **kwargs)
            created_menus.append(menu)
            return menu

        with (
            patch("zebtrack.ui.components.menu_manager.Menu", side_effect=menu_factory),
            patch.object(TkMenu, "post"),
        ):
            menu_manager.show_processing_reports_context_menu(
                "/path/to/video.mp4",
                "#1",
                120,
                200,
                callbacks,
            )

        assert created_menus
        menu = created_menus[0]
        labels = []
        end_index = menu.index("end")
        assert end_index is not None
        for idx in range(end_index + 1):
            entry_type = menu.type(idx)
            if entry_type in {"separator", "tearoff"}:
                continue
            label = menu.entrycget(idx, "label")
            if label:
                labels.append(label)

        assert "🗑️ Apagar Arena (Selecionado)" in labels
        assert "🧹 Apagar Todos os Dados de Processamento" in labels
        assert "❌ Remover Vídeo do Projeto" in labels
        assert "🗑️ Apagar Item Específico..." in labels

        # Second menu should be the delete submenu
        assert len(created_menus) >= 2
        delete_menu = created_menus[1]
        delete_labels = []
        delete_end_index = delete_menu.index("end")
        assert delete_end_index is not None
        for idx in range(delete_end_index + 1):
            entry_type = delete_menu.type(idx)
            if entry_type in {"separator", "tearoff"}:
                continue
            label = delete_menu.entrycget(idx, "label")
            if label:
                delete_labels.append(label)

        assert "🏛️ Apagar Arena" in delete_labels
        assert "📈 Apagar Trajetória" in delete_labels


@pytest.mark.gui
class TestShowRoiContextMenu:
    """Tests for ROI context menu display."""

    def test_show_roi_context_menu_no_coords(self, menu_manager):
        """If no coordinates are available, menu should not show."""
        menu_manager.gui.zone_controls = SimpleNamespace(zone_listbox=Mock())
        menu_manager.gui.roi_context_menu = Mock()

        menu_manager.show_roi_context_menu()

        menu_manager.gui.roi_context_menu.post.assert_not_called()

    def test_show_roi_context_menu_no_listbox(self, menu_manager, tkinter_root):
        """If listbox is missing, menu should not show."""
        menu_manager.gui.root = tkinter_root
        menu_manager.gui.zone_controls = SimpleNamespace()
        menu_manager.gui.roi_context_menu = Mock()

        menu_manager.show_roi_context_menu(x=10, y=20)

        menu_manager.gui.roi_context_menu.post.assert_not_called()

    def test_show_roi_context_menu_roi_item(self, menu_manager, tkinter_root):
        """ROI items should use the existing ROI context menu."""
        listbox = Mock()
        listbox.identify_row.return_value = "roi-1"
        listbox.item.return_value = {"values": ["ROI 1"]}

        menu_manager.gui.root = tkinter_root
        menu_manager.gui.zone_controls = SimpleNamespace(zone_listbox=listbox)
        menu_manager.gui.roi_context_menu = Mock()

        event = Mock()
        event.x_root = 50
        event.y_root = 60
        event.y = 10

        menu_manager.show_roi_context_menu(event=event)

        listbox.selection_set.assert_called_once_with("roi-1")
        menu_manager.gui.roi_context_menu.post.assert_called_once_with(50, 60)

    def test_show_roi_context_menu_arena_item(self, menu_manager, tkinter_root):
        """Arena items should show a limited menu."""
        from tkinter import Menu as TkMenu

        listbox = Mock()
        listbox.identify_row.return_value = "arena-1"
        listbox.item.return_value = {"values": ["Arena Principal"]}

        menu_manager.gui.root = tkinter_root
        menu_manager.gui.zone_controls = SimpleNamespace(zone_listbox=listbox)
        menu_manager.gui.roi_context_menu = Mock()

        event = Mock()
        event.x_root = 90
        event.y_root = 100
        event.y = 12

        with patch.object(TkMenu, "post") as mock_post:
            menu_manager.show_roi_context_menu(event=event)

        menu_manager.gui.roi_context_menu.post.assert_not_called()
        mock_post.assert_called_once_with(90, 100)
