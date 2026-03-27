#!/usr/bin/env pwsh
# =============================================================================
# prepare_commit.ps1 — Auto-fix & stage for clean commits
# =============================================================================
# Runs pre-commit hooks to fix trailing whitespace, end-of-file, ruff, etc.
# Then re-stages any modified files so the next commit passes cleanly.
#
# Usage:
#   .\scripts\prepare_commit.ps1                  # Fix + stage
#   .\scripts\prepare_commit.ps1 -CommitMessage "feat: my change"  # Fix + stage + commit
# =============================================================================

param(
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ZebTrack-AI: Prepare Commit" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Run pre-commit on all staged files to auto-fix
Write-Host "[1/3] Running pre-commit hooks (auto-fix)..." -ForegroundColor Yellow
poetry run pre-commit run --all-files 2>&1 | Out-String | Write-Host
$precommitExit = $LASTEXITCODE

# Step 2: Re-stage any files that were modified by hooks
Write-Host ""
Write-Host "[2/3] Re-staging modified files..." -ForegroundColor Yellow

$modifiedFiles = git diff --name-only 2>&1
if ($modifiedFiles) {
    Write-Host "  Files fixed by pre-commit:" -ForegroundColor Gray
    $modifiedFiles | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
    git add -u
    Write-Host "  Staged successfully." -ForegroundColor Green
} else {
    Write-Host "  No additional modifications to stage." -ForegroundColor Green
}

# Step 3: Verify — re-run pre-commit to confirm all hooks pass
Write-Host ""
Write-Host "[3/3] Verifying all hooks pass..." -ForegroundColor Yellow
poetry run pre-commit run --all-files 2>&1 | Out-String | Write-Host
$verifyExit = $LASTEXITCODE

Write-Host ""
if ($verifyExit -eq 0) {
    Write-Host "All checks passed! Ready to commit." -ForegroundColor Green

    if ($CommitMessage -ne "") {
        Write-Host ""
        Write-Host "Committing with message: $CommitMessage" -ForegroundColor Cyan
        git commit -m $CommitMessage
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Commit successful!" -ForegroundColor Green
        } else {
            Write-Host "Commit failed. Check output above." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Run 'git commit' or use VS Code Source Control to commit." -ForegroundColor Gray
    }
} else {
    Write-Host "Some hooks still failing. Review the output above." -ForegroundColor Red
    exit 1
}

Write-Host ""
