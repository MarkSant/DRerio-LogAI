# PreToolUse hook: block direct pushes to main from inside Claude Code.
# Exits 2 (block) when the Bash command is a `git push` targeting `main`.
# Allows `git push --dry-run`, pushes to other branches, and `--force-with-lease`
# to non-main targets.

$ErrorActionPreference = 'SilentlyContinue'

try {
    $raw = $input | Out-String
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

    $payload = $raw | ConvertFrom-Json
    $cmd = $payload.tool_input.command
    if (-not $cmd) { exit 0 }

    # Only inspect git push commands
    if ($cmd -notmatch 'git\s+push') { exit 0 }

    # Allow dry runs explicitly
    if ($cmd -match '--dry-run') { exit 0 }

    # Block patterns that look like a push to main
    $pushesToMain = (
        $cmd -match 'git\s+push\s+\S+\s+(HEAD:)?main(\s|$)' -or
        $cmd -match 'git\s+push.*\smain:main' -or
        $cmd -match 'git\s+push.*\sHEAD:main(\s|$)'
    )

    if ($pushesToMain) {
        [Console]::Error.WriteLine("=" * 70)
        [Console]::Error.WriteLine("BLOCKED: direct git push to main from Claude Code.")
        [Console]::Error.WriteLine("Use a feature branch + PR, or run the command manually outside Claude.")
        [Console]::Error.WriteLine("Hook: .claude/hooks/block-push-main.ps1")
        [Console]::Error.WriteLine("=" * 70)
        exit 2
    }
} catch {
    # On any error parsing, do not block.
    exit 0
}

exit 0
