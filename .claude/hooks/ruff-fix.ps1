# PostToolUse hook: silently run `ruff check --fix` on the .py file just edited.
# Invoked by Claude Code after Edit/Write tools succeed.
# Always exits 0 — this hook never blocks the agent.

$ErrorActionPreference = 'SilentlyContinue'

try {
    $raw = $input | Out-String
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

    $payload = $raw | ConvertFrom-Json
    $filePath = $payload.tool_input.file_path
    if (-not $filePath) { exit 0 }

    # Only act on Python files inside the repo
    if ($filePath -notmatch '\.py$') { exit 0 }
    if ($filePath -notmatch '(src[\\/]zebtrack|tests)[\\/]') { exit 0 }

    # Run ruff fix quietly. Discard all output; never block on lint errors.
    & poetry run ruff check --fix --quiet -- "$filePath" *> $null
} catch {
    # Swallow any error — never block the agent on hook failure.
}

exit 0
