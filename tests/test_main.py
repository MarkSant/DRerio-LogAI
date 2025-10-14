from unittest.mock import patch

import pytest

# We need to import the function we want to test
from zebtrack.__main__ import main


@patch("zebtrack.__main__.settings", None)
@patch("zebtrack.__main__.AppController")
@patch("zebtrack.__main__.messagebox")
@patch("zebtrack.__main__.tk")
@patch("sys.exit")
def test_main_handles_settings_load_failure(mock_exit, mock_tk, mock_messagebox, mock_controller):
    """
    Tests that the main function correctly handles the case where the
    global `settings` object is None.
    """
    # Configure the mock_exit to raise an exception, which simulates the
    # halting of the program.
    mock_exit.side_effect = SystemExit(1)

    # We expect main() to call sys.exit(1), which we've mocked to raise
    # SystemExit. We can catch this exception to verify it was called.
    with pytest.raises(SystemExit) as e:
        main()

    # Assert that the exit code was 1
    assert e.value.code == 1

    # Assert that the application showed an error and tried to exit.
    mock_messagebox.showerror.assert_called_once()
    assert "Fatal Configuration Error" in mock_messagebox.showerror.call_args.args[0]
    mock_exit.assert_called_once_with(1)

    # Assert that the main application controller was NOT initialized
    mock_controller.assert_not_called()
