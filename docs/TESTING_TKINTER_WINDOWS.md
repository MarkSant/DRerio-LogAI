# Tkinter Testing on Windows - Known Issues and Solutions

## Problem Description

When running multiple GUI tests using Tkinter on Windows, tests may fail with errors like:

```
_tkinter.TclError: Can't find a usable init.tcl in the following directories:
_tkinter.TclError: Can't find a usable tk.tcl in the following directories:
```

These errors occur **even when Tkinter is properly installed** and work fine in individual executions.

## Root Cause

This is a **known bug in Tkinter on Windows** where creating multiple `tk.Tk()` instances sequentially can corrupt the internal references to Tcl/Tk library paths. After a few instances are created and destroyed, the Tcl interpreter loses track of its library directories.

### Why It Happens

1. Each `tk.Tk()` creates a new Tcl/Tk interpreter
2. On Windows, the Tcl library path registration is not always properly reset between instances
3. After multiple create/destroy cycles, path corruption occurs
4. Subsequent `tk.Tk()` calls cannot find required Tcl/Tk files

## Diagnosis Steps

### 1. Verify Tkinter Works Outside Tests

```powershell
# Test basic Tkinter functionality
python -c "import tkinter; print('Tkinter version:', tkinter.TkVersion); root = tkinter.Tk(); print('Success'); root.destroy()"

# Test in Poetry environment
poetry run python -c "import tkinter; root = tkinter.Tk(); print('Success in Poetry'); root.destroy()"
```

If these work, Tkinter is installed correctly - the problem is test-specific.

### 2. Identify the Pattern

- First few tests pass ✅
- Later tests fail with Tcl/Tk path errors ❌
- Tests work fine individually
- Tests fail when run as a suite

This pattern confirms the multiple `tk.Tk()` instance bug.

## Solution: Session-Scoped Fixture with Toplevel Windows

Instead of creating multiple `tk.Tk()` instances, create **one root window per test session** and use `tk.Toplevel()` for individual tests.

### Implementation

Update `tests/conftest.py`:

```python
import tkinter as tk
import pytest

@pytest.fixture(scope="session")
def tkinter_session_root():
    """
    Session-scoped fixture for a shared tkinter root window.
    
    This avoids the Tkinter bug on Windows where multiple Tk() instances
    can corrupt the Tcl/Tk library paths.
    """
    display = None

    # Only use virtual display on Linux/Unix systems
    if platform.system() == "Linux":
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(800, 600))
            display.start()
        except ImportError:
            pass
        except Exception as e:
            warnings.warn(f"Could not start virtual display: {e}", stacklevel=2)

    # Create the tkinter root window (once per session)
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()

    yield root

    # Clean up at end of session
    try:
        root.quit()
        root.destroy()
    except Exception:
        pass

    if display is not None:
        try:
            display.stop()
        except Exception:
            pass


@pytest.fixture
def tkinter_root(tkinter_session_root):
    """
    Function-scoped fixture that reuses the session root.
    
    Creates a Toplevel window for each test to ensure isolation,
    avoiding the Tkinter multi-instance bug on Windows.
    """
    # Create a Toplevel window for this test (not a new Tk instance)
    test_window = tk.Toplevel(tkinter_session_root)
    test_window.withdraw()
    test_window.update_idletasks()

    yield test_window

    # Clean up only this test's window
    try:
        # Destroy all child widgets
        for widget in test_window.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass
        
        # Destroy the test window
        test_window.update_idletasks()
        test_window.destroy()
    except tk.TclError:
        pass
    except Exception:
        pass
```

### Key Points

1. **`tkinter_session_root`**: Creates ONE `tk.Tk()` instance for the entire test session
2. **`tkinter_root`**: Creates `tk.Toplevel()` windows for each test
3. **Isolation**: Each test gets its own window but shares the root Tk instance
4. **Cleanup**: Properly destroys Toplevel windows without destroying the session root

## Benefits

✅ **No more Tcl/Tk path errors**  
✅ **Tests can run as a suite**  
✅ **Maintains test isolation**  
✅ **Works on all platforms (Windows, Linux, macOS)**  
✅ **Faster test execution** (no repeated Tk initialization)

## Testing the Solution

```powershell
# Run all GUI tests
poetry run pytest tests/ui/components/ -v -n0 -m gui

# Run specific test file multiple times
poetry run pytest tests/ui/components/test_analysis_display.py -v -n0 -m gui

# Run with coverage
poetry run pytest tests/ui/components/ -v -n0 -m gui --cov=zebtrack --cov-report=html
```

## Alternative Approaches (Not Recommended)

### ❌ Using `pytest-xdist` with `-n1`
- Spawns separate processes which is slower
- Doesn't solve the root cause
- Can still fail with certain test patterns

### ❌ Setting `TCL_LIBRARY` and `TK_LIBRARY` environment variables
- Platform-specific
- Requires hardcoded paths
- Doesn't address the underlying bug

### ❌ Recreating Tk() with delays
- Unreliable
- Makes tests slower
- Still fails eventually

## References

- **Tkinter Bug Report**: https://bugs.python.org/issue37474
- **Windows Tk Path Issues**: https://github.com/python/cpython/issues/85720
- **pytest Fixture Scopes**: https://docs.pytest.org/en/stable/fixture.html#scope-sharing-fixtures-across-classes-modules-packages-or-session

## Related Files

- `tests/conftest.py` - Fixture implementations
- `tests/ui/components/test_analysis_display.py` - Example GUI tests
- `tests/ui/components/test_arduino_dashboard.py` - Example GUI tests
- `tests/ui/dialogs/test_live_config_dialog.py` - Example dialog tests

## Version Info

- **Python**: 3.12+
- **tkinter**: 8.6
- **Platform**: Windows 10/11
- **pytest**: 8.4.1+

## Last Updated

October 31, 2025 - Initial documentation after resolving issue in PR #228
