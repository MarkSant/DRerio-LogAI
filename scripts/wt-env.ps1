<#
.SYNOPSIS
    Point the shell at the main .venv's tools and THIS worktree's sources.

.DESCRIPTION
    Dot-source it from anywhere inside a worktree or the main repo:

        . .\scripts\wt-env.ps1

    Why this is needed at all
    -------------------------
    Git worktrees share the repository but not the environment, and two
    details of this project's setup make that bite:

    1. The worktree's own .venv is a poetry stub: Python 3.14 with pip and
       nothing else, while the project runs on 3.12. So mypy, pytest and ruff
       are simply absent there, and every pre-commit / pre-push hook that
       shells out to them dies with "'mypy' is not recognized".

    2. The main .venv resolves zebtrack through
       site-packages\drerio_logai.pth, which holds an ABSOLUTE path to the
       MAIN repository's src\. Borrowing the main venv without correcting
       PYTHONPATH therefore runs the main branch's code from inside your
       worktree. That failure is silent: the suite goes green without having
       exercised one line of your changes.

    Dot-sourcing this fixes both, and because git hooks inherit the
    environment of the process that launched them, git commit and git push
    start working too - with the real gates running, not skipped.

    Idempotent: safe to dot-source repeatedly in the same session.
#>

$worktree = (git rev-parse --show-toplevel 2>$null)
if (-not $worktree) {
    Write-Error "wt-env: not inside a git repository"
    return
}
$worktree = $worktree.Trim().Replace('/', '\')

# --git-common-dir points at the MAIN repo's .git even from a worktree.
$mainGit = (git rev-parse --git-common-dir).Trim().Replace('/', '\')
if (-not [System.IO.Path]::IsPathRooted($mainGit)) {
    $mainGit = Join-Path $worktree $mainGit
}
$mainRoot = (Resolve-Path (Join-Path $mainGit '..')).Path

$venvScripts = Join-Path $mainRoot '.venv\Scripts'
if (-not (Test-Path (Join-Path $venvScripts 'python.exe'))) {
    Write-Error "wt-env: no usable venv at $mainRoot\.venv - run 'poetry install' in the main repo"
    return
}

if (($env:PATH -split ';') -notcontains $venvScripts) {
    $env:PATH = "$venvScripts;$env:PATH"
}

# Prepended, so it wins over drerio_logai.pth in site-packages.
$srcPath = Join-Path $worktree 'src'
if (($env:PYTHONPATH -split ';') -notcontains $srcPath) {
    if ($env:PYTHONPATH) { $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH" }
    else { $env:PYTHONPATH = $srcPath }
}

Write-Output "wt-env: tools from $mainRoot\.venv"
Write-Output "wt-env: sources from $srcPath"

if ((Test-Path (Join-Path $worktree '.venv\pyvenv.cfg')) -and ($worktree -ne $mainRoot)) {
    Write-Warning "wt-env: this worktree has its own stub .venv. Avoid 'poetry run' here; it would select that one."
}
