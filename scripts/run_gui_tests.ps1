# ==============================================================================
# DRerio LogAI GUI Tests Runner
# ==============================================================================
#
# Purpose:
#   Helper script to execute GUI tests correctly with serial execution (-n0)
#   to prevent TclError "Can't find a usable tk.tcl" failures.
#
# Problem:
#   ttkbootstrap.Style maintains global state (singleton) that conflicts when
#   pytest-xdist runs tests in parallel workers. This causes Tkinter/Tcl
#   initialization failures.
#
# Solution:
#   Always run GUI tests with -n0 (serial execution)
#
# Usage:
#   .\scripts\run_gui_tests.ps1              # Run all GUI tests
#   .\scripts\run_gui_tests.ps1 -Verbose     # With verbose output
#   .\scripts\run_gui_tests.ps1 -Coverage    # With coverage report
#
# ==============================================================================

param(
    [switch]$Verbose,
    [switch]$Coverage,
    [string]$TestPath = ""
)

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  DRerio LogAI GUI Tests Runner" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Build pytest command
$command = "poetry run pytest -m gui -n0"

if ($Verbose) {
    $command += " -v"
    Write-Host "✓ Verbose output enabled" -ForegroundColor Green
} else {
    $command += " -q"
}

if ($Coverage) {
    Write-Host "✓ Coverage reporting enabled" -ForegroundColor Green
} else {
    $command += " --no-cov"
    Write-Host "✓ Coverage disabled (faster execution)" -ForegroundColor Green
}

if ($TestPath -ne "") {
    $command += " $TestPath"
    Write-Host "✓ Running specific test: $TestPath" -ForegroundColor Green
} else {
    Write-Host "✓ Running all GUI tests" -ForegroundColor Green
}

Write-Host ""
Write-Host "⚙️  Configuration:" -ForegroundColor Yellow
Write-Host "   - Serial execution (-n0): REQUIRED for GUI tests" -ForegroundColor Gray
Write-Host "   - Marker filter: -m gui" -ForegroundColor Gray
Write-Host ""
Write-Host "🚀 Executing: $command" -ForegroundColor Magenta
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Execute the command
Invoke-Expression $command
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if ($exitCode -eq 0) {
    Write-Host "✅ All GUI tests passed!" -ForegroundColor Green
} else {
    Write-Host "❌ Some GUI tests failed (exit code: $exitCode)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Verify Tkinter installation:" -ForegroundColor Gray
    Write-Host "     poetry run python -c `"import tkinter; root = tkinter.Tk(); print('OK'); root.destroy()`"" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. Run specific test in isolation:" -ForegroundColor Gray
    Write-Host "     poetry run pytest tests/ui/test_gui.py::test_name -n0 -v" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  3. Check for ttkbootstrap singleton issues:" -ForegroundColor Gray
    Write-Host "     poetry run pytest tests/ui/test_components.py" -ForegroundColor Gray
}

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

exit $exitCode
