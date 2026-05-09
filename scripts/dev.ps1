# ZebTrack-AI Development Helper Script
# Usage: .\scripts\dev.ps1 <command> [args...]
#
# This script is the universal entry point for the project's
# day-to-day commands. Any AI agent (Copilot, Cursor, Claude Code,
# Gemini, etc.) and any human dev should drive routine tasks
# through here so we have one source of truth.

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Rest
)

function Show-Help {
    Write-Host 'ZebTrack-AI Development Commands' -ForegroundColor Cyan
    Write-Host '=================================' -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Usage: .\scripts\dev.ps1 <command> [args...]' -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Available Commands:' -ForegroundColor Green
    Write-Host '  test              Run fast test suite (pytest -q; excludes GUI/slow)' -ForegroundColor White
    Write-Host '  test-fast         Alias for test (explicit name for AI agents)' -ForegroundColor White
    Write-Host '  test-gui          Run GUI tests (pytest -m gui -n0; sequential)' -ForegroundColor White
    Write-Host '  test-verbose      Run tests with verbose output (pytest -v)' -ForegroundColor White
    Write-Host '  test-overlay      Run overlay integration tests' -ForegroundColor White
    Write-Host '  test-intervals    Run interval persistence tests' -ForegroundColor White
    Write-Host '  test-coverage     Run tests with coverage report' -ForegroundColor White
    Write-Host '  lint              Check code style with Ruff' -ForegroundColor White
    Write-Host '  lint-fix          Auto-fix linting issues' -ForegroundColor White
    Write-Host '  impact            Run impact analyzer. Args: <type> <name>' -ForegroundColor White
    Write-Host '                    e.g.  .\scripts\dev.ps1 impact class WeightManager' -ForegroundColor DarkGray
    Write-Host '  check-all         Run lint + fast test suite' -ForegroundColor White
    Write-Host '  run               Launch ZebTrack-AI GUI' -ForegroundColor White
    Write-Host '  install           Install dependencies via Poetry' -ForegroundColor White
    Write-Host '  update            Update dependencies' -ForegroundColor White
    Write-Host '  clean             Remove build artifacts and cache files' -ForegroundColor White
    Write-Host ''
}

switch ($Command.ToLower()) {
    'test' {
        Write-Host 'Running fast test suite (excludes GUI/slow)...' -ForegroundColor Cyan
        poetry run pytest -q
    }
    'test-fast' {
        Write-Host 'Running fast test suite (excludes GUI/slow)...' -ForegroundColor Cyan
        poetry run pytest -q
    }
    'test-gui' {
        Write-Host 'Running GUI tests sequentially. This may take a few minutes.' -ForegroundColor Cyan
        poetry run pytest -m gui -n0
    }
    'test-verbose' {
        Write-Host 'Running tests (verbose)...' -ForegroundColor Cyan
        poetry run pytest -v
    }
    'test-overlay' {
        Write-Host 'Running overlay integration tests...' -ForegroundColor Cyan
        poetry run pytest tests/test_overlay_integration.py -v
    }
    'test-intervals' {
        Write-Host 'Running interval persistence tests...' -ForegroundColor Cyan
        poetry run pytest tests/test_interval_frames_config.py -v
    }
    'test-coverage' {
        Write-Host 'Running tests with coverage...' -ForegroundColor Cyan
        poetry run pytest --cov=zebtrack --cov-report=html --cov-report=term
        Write-Host ''
        Write-Host 'Coverage report generated in htmlcov/index.html' -ForegroundColor Green
    }
    'lint' {
        Write-Host 'Checking code style with Ruff...' -ForegroundColor Cyan
        poetry run ruff check .
    }
    'lint-fix' {
        Write-Host 'Auto-fixing linting issues...' -ForegroundColor Cyan
        poetry run ruff check . --fix
    }
    'impact' {
        if (-not $Rest -or $Rest.Count -lt 2) {
            Write-Host 'Usage: .\scripts\dev.ps1 impact <type> <name>' -ForegroundColor Red
            Write-Host '  type: file | class | function | event | settings | di | graph' -ForegroundColor DarkGray
            Write-Host '  e.g.  .\scripts\dev.ps1 impact class WeightManager' -ForegroundColor DarkGray
            exit 1
        }
        Write-Host ('Running impact analysis: {0} {1}...' -f $Rest[0], $Rest[1]) -ForegroundColor Cyan
        poetry run python scripts/impact_analyzer.py @Rest
    }
    'check-all' {
        Write-Host 'Running full validation...' -ForegroundColor Cyan
        Write-Host ''
        Write-Host '[1/2] Linting...' -ForegroundColor Yellow
        poetry run ruff check .
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Linting failed! Fix errors before continuing.' -ForegroundColor Red
            exit 1
        }
        Write-Host ''
        Write-Host '[2/2] Testing...' -ForegroundColor Yellow
        poetry run pytest -q
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Tests failed!' -ForegroundColor Red
            exit 1
        }
        Write-Host ''
        Write-Host 'All checks passed!' -ForegroundColor Green
    }
    'run' {
        Write-Host 'Launching ZebTrack-AI...' -ForegroundColor Cyan
        poetry run zebtrack
    }
    'install' {
        Write-Host 'Installing dependencies...' -ForegroundColor Cyan
        poetry install
    }
    'update' {
        Write-Host 'Updating dependencies...' -ForegroundColor Cyan
        poetry update
    }
    'clean' {
        Write-Host 'Cleaning build artifacts and cache...' -ForegroundColor Cyan
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .pytest_cache, __pycache__, dist, build, *.egg-info, .coverage, htmlcov
        Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
        Get-ChildItem -Recurse -Filter '*.pyc' | Remove-Item -Force
        Write-Host 'Clean complete!' -ForegroundColor Green
    }
    'help' {
        Show-Help
    }
    default {
        Write-Host ('Unknown command: {0}' -f $Command) -ForegroundColor Red
        Write-Host ''
        Show-Help
        exit 1
    }
}
