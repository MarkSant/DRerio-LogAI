# ==============================================================================
# ZebTrack-AI - Run GUI tests on changed files only
# ==============================================================================
#
# Purpose:
#   Runs GUI tests (-m gui -n0) ONLY on test files that have been modified
#   relative to the default branch (main) or staged for commit.
#   Designed to catch CI-breaking GUI regressions locally on Windows before push.
#
# Usage:
#   .\scripts\test_gui_changed.ps1              # Tests changed GUI files
#   .\scripts\test_gui_changed.ps1 -All         # Falls back to all GUI tests
#   .\scripts\test_gui_changed.ps1 -Verbose     # Verbose pytest output
#   .\scripts\test_gui_changed.ps1 -Base develop # Compare against develop branch
#
# ==============================================================================

param(
    [switch]$All,
    [switch]$Verbose,
    [string]$Base = "main"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ZebTrack-AI - GUI Test Runner (Changed Files)" -ForegroundColor Cyan
Write-Host "  ==============================================" -ForegroundColor Cyan
Write-Host ""

if ($All) {
    Write-Host "  Mode: ALL GUI tests" -ForegroundColor Yellow
    $testFiles = @()
} else {
    # Collect test files changed vs base branch + staged + unstaged
    $changedFiles = @()

    # Files changed vs remote base (for pre-push)
    $remoteDiff = git diff --name-only "origin/$Base" -- "tests/" 2>$null
    if ($remoteDiff) { $changedFiles += $remoteDiff }

    # Staged files
    $staged = git diff --cached --name-only -- "tests/" 2>$null
    if ($staged) { $changedFiles += $staged }

    # Unstaged working-tree changes
    $unstaged = git diff --name-only -- "tests/" 2>$null
    if ($unstaged) { $changedFiles += $unstaged }

    # Deduplicate and filter to GUI-relevant test files
    $testFiles = $changedFiles |
        Sort-Object -Unique |
        Where-Object { $_ -match "^tests/" -and $_ -match "\.py$" } |
        Where-Object { Test-Path $_ }

    if ($testFiles.Count -eq 0) {
        Write-Host "  No changed test files detected. Nothing to run." -ForegroundColor Green
        Write-Host ""
        exit 0
    }

    Write-Host "  Changed test files ($($testFiles.Count)):" -ForegroundColor Yellow
    foreach ($f in $testFiles) {
        Write-Host "    - $f" -ForegroundColor Gray
    }
    Write-Host ""
}

# Build pytest command
$pytestArgs = @("-m", "gui", "-n0", "--no-cov", "--tb=short")

if ($Verbose) {
    $pytestArgs += "-v"
} else {
    $pytestArgs += "-q"
}

if (-not $All -and $testFiles.Count -gt 0) {
    $pytestArgs += $testFiles
}

$cmdDisplay = "poetry run pytest " + ($pytestArgs -join " ")
Write-Host "  Command: $cmdDisplay" -ForegroundColor Magenta
Write-Host ""

# Execute
poetry run pytest @pytestArgs
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "  All GUI tests passed!" -ForegroundColor Green
} elseif ($exitCode -eq 5) {
    # pytest exit code 5 = no tests collected (none matched -m gui)
    Write-Host "  No GUI tests in the changed files. OK." -ForegroundColor Green
    $exitCode = 0
} else {
    Write-Host "  GUI tests failed (exit code: $exitCode)" -ForegroundColor Red
    Write-Host "  Fix these before pushing to avoid CI failures." -ForegroundColor Yellow
}

Write-Host ""
exit $exitCode
