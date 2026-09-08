<#
.SYNOPSIS
    One-time setup for DRerio LogAI on Windows: dependencies, detector weights,
    and a desktop shortcut.

.DESCRIPTION
    Written for the researcher who operates the software rather than develops
    it. It performs the four steps of the documented install and stops at the
    first one that fails, naming what to do about it -- because the failures in
    this particular install do not describe themselves:

      * A wrong Python leaves the project uninstalled, and the NEXT command is
        the one that reports "No module named 'zebtrack'".
      * Missing weights let the app start and then refuse to track.

    Run once, from the repository folder:

        powershell -ExecutionPolicy Bypass -File install.ps1

    or double-click install.bat, which does exactly that.

.PARAMETER Dev
    Also install the development dependency group and the pre-commit hooks.

.PARAMETER SkipShortcut
    Do not create the desktop and Start Menu shortcuts.

.PARAMETER SkipWeights
    Do not download the detector models. The application will not track until
    they are fetched; use this only on a machine that already has them.
#>
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$SkipShortcut,
    [switch]$SkipWeights
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot

# Poetry, pip and Python all emit UTF-8; without this a Windows console in a
# non-English locale mangles their output into mojibake mid-install.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

function Write-Step {
    param([int]$Number, [int]$Total, [string]$Text)
    Write-Host ''
    Write-Host "[$Number/$Total] $Text" -ForegroundColor Cyan
}

function Write-Problem {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text -ForegroundColor Yellow
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$TotalSteps = 4

# --------------------------------------------------------------------------
# 1. Python
# --------------------------------------------------------------------------
# The supported range is >=3.12,<3.14 (pyproject.toml). The ceiling is not
# conservatism: the pinned numpy publishes wheels only up to cp313, so on 3.14
# the install tries to compile numpy from source, fails, and leaves the project
# uninstalled -- a state that only announces itself one command later.
Write-Step 1 $TotalSteps 'Checking Python'

# The probe prints an INTEGER (312, 313) on purpose. PowerShell strips quotes
# when it hands arguments to a native executable, so the obvious
# `print("%d.%d" % ...)` reaches python as `print(%d.%d % ...)` and dies with a
# SyntaxError -- which this loop would read as "no Python here" and report as a
# missing interpreter. Keeping the snippet free of string literals sidesteps
# the quoting entirely.
$python = $null
$pythonVersion = $null
foreach ($candidate in @('py -3.12', 'py -3.13', 'python')) {
    $exe, $arg = $candidate -split ' ', 2
    if (-not (Test-CommandExists $exe)) { continue }
    try {
        $probe = 'import sys; print(sys.version_info[0]*100 + sys.version_info[1])'
        # 2>$null: `py -3.13` on a machine without it writes a multi-line
        # "No suitable Python runtime found" block that is noise here.
        $code = if ($arg) { & $exe $arg -c $probe 2>$null } else { & $exe -c $probe 2>$null }
    } catch { continue }
    if ($LASTEXITCODE -ne 0) { continue }

    $code = [int]($code | Select-Object -Last 1)
    $pretty = "$([math]::Floor($code / 100)).$($code % 100)"
    if ($code -in @(312, 313)) {
        $python = $candidate
        $pythonVersion = $pretty
        Write-Host "  Using Python $pretty ($candidate)"
        break
    }
    Write-Host "  Ignoring Python $pretty ($candidate) - outside the supported range"
}

if (-not $python) {
    Write-Problem @"
No supported Python found. DRerio LogAI needs Python 3.12 (3.13 also works).

Install it from:
    https://www.python.org/downloads/release/python-3129/

Download "Windows installer (64-bit)". On the FIRST screen of the installer,
tick "Add python.exe to PATH" before clicking Install -- without it, this
script and Poetry cannot find the interpreter.

Then close this window, open a new one, and run install.ps1 again.
"@
    exit 1
}

# --------------------------------------------------------------------------
# 2. Poetry
# --------------------------------------------------------------------------
Write-Step 2 $TotalSteps 'Checking Poetry'

if (Test-CommandExists 'poetry') {
    Write-Host "  $(poetry --version)"
}
else {
    Write-Problem @"
Poetry is not installed (or not on PATH). It is the tool that installs the
application's dependencies.

Install it with the official installer:

    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

The installer prints the folder it installed into -- typically
%APPDATA%\Python\Scripts. Add that folder to your PATH, then close this window,
open a new one, and run install.ps1 again.

Full instructions: https://python-poetry.org/docs/#installation
"@
    exit 1
}

# --------------------------------------------------------------------------
# 3. Dependencies
# --------------------------------------------------------------------------
Write-Step 3 $TotalSteps 'Installing dependencies (this takes several minutes)'

# Pin the environment to the interpreter validated above. Poetry otherwise
# builds it from whichever python it finds first, which on a machine with 3.14
# installed alongside is the one that breaks.
$pythonExe = if ($python -like 'py *') {
    $ver = ($python -split ' ')[1]
    (& py $ver -c 'import sys; print(sys.executable)')
} else {
    (& python -c 'import sys; print(sys.executable)')
}
Write-Host "  Environment will use Python $pythonVersion at $pythonExe"

Push-Location $RepoRoot
try {
    & poetry env use $pythonExe
    if ($LASTEXITCODE -ne 0) { throw "poetry env use failed (exit $LASTEXITCODE)" }

    if ($Dev) { & poetry install --with dev } else { & poetry install }
    if ($LASTEXITCODE -ne 0) {
        Write-Problem @"
'poetry install' failed. Nothing here needs a C compiler -- every dependency
ships as a prebuilt wheel -- so the usual causes are a dropped network
connection or not enough free disk (the environment needs about 1.7 GB).

Fix the cause and run install.ps1 again; it resumes rather than starting over.
"@
        exit 1
    }

    # The install is only real if the package imports. Poetry reports success
    # for a run that resolved everything and still left the project itself
    # uninstalled, and that is precisely the state that surfaces later as
    # "No module named 'zebtrack'".
    & poetry run python -c "import zebtrack" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Problem @"
Dependencies installed, but the 'zebtrack' package itself did not. Check which
interpreter the environment was built on:

    poetry run python -V

It must report 3.12 or 3.13. If it does not, delete the .venv folder and run
install.ps1 again.
"@
        exit 1
    }
    Write-Host '  Dependencies installed.'

    if ($Dev) {
        & poetry run pre-commit install
        if ($LASTEXITCODE -ne 0) { Write-Warning 'pre-commit hooks were not installed.' }
    }

    # ----------------------------------------------------------------------
    # 4. Detector weights
    # ----------------------------------------------------------------------
    Write-Step 4 $TotalSteps 'Downloading detector models (~250 MB)'

    if ($SkipWeights) {
        Write-Host '  Skipped (-SkipWeights).'
    }
    else {
        & poetry run fetch-weights
        if ($LASTEXITCODE -ne 0) {
            Write-Problem @"
The detector models were not downloaded. The application will start but cannot
track until they are present.

Retry with:
    poetry run fetch-weights

The download resumes from scratch but verifies every file against a recorded
SHA-256, so an interrupted attempt is discarded rather than half-kept.
"@
            exit 1
        }
    }
}
finally {
    Pop-Location
}

# --------------------------------------------------------------------------
# Shortcut
# --------------------------------------------------------------------------
if (-not $SkipShortcut) {
    Write-Host ''
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'scripts\install_shortcut.ps1')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'The shortcut could not be created. Start the app with: poetry run zebtrack'
    }
}

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
if ($SkipShortcut) {
    Write-Host 'Start the application with:  poetry run zebtrack'
}
else {
    Write-Host 'Start the application from the "DRerio LogAI" icon on your Desktop.'
}
Write-Host ''
