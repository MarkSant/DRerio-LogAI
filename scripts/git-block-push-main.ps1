# Git pre-push hook — block direct pushes to main.
# Driven by pre-commit framework (.pre-commit-config.yaml; pre-push stage).
# Universal: works for any tool that uses git (Copilot, Cursor, Claude Code,
# plain CLI, etc.) once the user has run `pre-commit install --hook-type pre-push`.
#
# Behavior:
#   - exits 0 if no main-targeted ref is being pushed (or pre-commit didn't
#     pass push refs, in which case we fall back to checking the current branch)
#   - exits 1 with a clear message if pushing main directly
#
# To bypass intentionally (rare): `git push --no-verify`. Document why in the
# commit message.

$ErrorActionPreference = 'Stop'

function Block-Push {
    param([string]$Reason)
    Write-Host '======================================================================' -ForegroundColor Red
    Write-Host 'BLOCKED: direct git push to main is not allowed.' -ForegroundColor Red
    Write-Host $Reason -ForegroundColor Yellow
    Write-Host 'Use a feature branch and open a pull request.' -ForegroundColor Yellow
    Write-Host 'Bypass (rare, document why): git push --no-verify' -ForegroundColor DarkGray
    Write-Host 'Hook: scripts/git-block-push-main.ps1' -ForegroundColor DarkGray
    Write-Host '======================================================================' -ForegroundColor Red
    exit 1
}

# Pre-commit's pre-push stage passes refs via stdin: "<localref> <localsha> <remoteref> <remotesha>"
$stdin = @($input)
$sawRefs = $false

foreach ($line in $stdin) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $sawRefs = $true
    $parts = $line -split '\s+'
    if ($parts.Count -lt 3) { continue }

    $localRef = $parts[0]
    $remoteRef = $parts[2]

    # Block any push whose remote ref is main (refs/heads/main)
    if ($remoteRef -match '^refs/heads/main$') {
        Block-Push -Reason ("Refusing to push '{0}' to '{1}'." -f $localRef, $remoteRef)
    }
}

# Fallback: if pre-commit didn't supply refs (some invocation modes), check the
# currently checked-out branch as a last-resort guard.
if (-not $sawRefs) {
    try {
        $branch = (& git symbolic-ref --quiet --short HEAD 2>$null).Trim()
        if ($branch -eq 'main') {
            Block-Push -Reason 'Current branch is main and no ref info was provided by pre-commit.'
        }
    } catch {
        # If git isn't available, do not block — fail-open is safer than fail-closed here.
    }
}

exit 0
