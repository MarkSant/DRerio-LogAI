<#
.SYNOPSIS
    One-time setup for DRerio LogAI on Windows: Python, Poetry, dependencies,
    detector weights, and a desktop shortcut.

.DESCRIPTION
    Written for the researcher who operates the software rather than develops
    it, and who may never have opened a terminal. It performs the documented
    install and stops at the first step that fails, naming what to do about it
    -- because the failures in this particular install do not describe
    themselves:

      * A wrong Python leaves the project uninstalled, and the NEXT command is
        the one that reports "No module named 'zebtrack'".
      * Missing weights let the app start and then refuse to track.

    Missing prerequisites are INSTALLED, after asking, rather than reported.
    Until 7.2.0 a machine without Poetry got a PowerShell one-liner and an
    instruction to "add that folder to your PATH" -- the single step of the
    install that the people this script is written for could not perform.

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

.PARAMETER Yes
    Answer "yes" to every offer to install a missing prerequisite (Python 3.12
    through winget, Poetry through its official installer). For unattended runs.
#>
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$SkipShortcut,
    [switch]$SkipWeights,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$RepoRoot = $PSScriptRoot

# Poetry, pip and Python all emit UTF-8; without this a Windows console in a
# non-English locale mangles their output into mojibake mid-install.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
# Everything above the dot-source guard below is a function, so the tests can
# load this file with `. .\install.ps1` and drive the helpers without running
# an installation.

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

function Confirm-Offer {
    <#
    Ask a yes/no question, defaulting to yes. Returns $false when there is no
    one to ask (a -NonInteractive host makes Read-Host throw), so an unattended
    run without -Yes declines instead of hanging.
    #>
    param([string]$Question)
    if ($Yes) {
        Write-Host "  $Question -> yes (-Yes)"
        return $true
    }
    try {
        $answer = Read-Host "  $Question [Y/n]"
    }
    catch {
        return $false
    }
    return ($answer.Trim() -eq '' -or $answer.Trim() -match '^(y|yes|s|sim)$')
}

function Add-PathEntry {
    <#
    Return $PathList with $Directory appended, unless an equivalent entry is
    already there (case-insensitive, trailing backslash ignored). An existing
    entry returns $PathList byte for byte, so the caller can tell "nothing to
    write" by comparing strings.
    #>
    param([string]$PathList, [string]$Directory)
    if ($null -eq $PathList) { $PathList = '' }
    $wanted = $Directory.TrimEnd('\')
    foreach ($entry in ($PathList -split ';')) {
        if ($entry -and ($entry.TrimEnd('\') -ieq $wanted)) {
            return $PathList
        }
    }
    if ($PathList.TrimEnd(';') -eq '') { return $wanted }
    return "$($PathList.TrimEnd(';'));$wanted"
}

function Update-SessionPath {
    # A program installed a moment ago (winget, the Poetry installer) edits the
    # PATH in the registry; this process still holds the PATH it started with.
    $merged = $env:Path
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    foreach ($entry in ("$machine;$user" -split ';')) {
        if ($entry) { $merged = Add-PathEntry $merged $entry }
    }
    $env:Path = $merged
}

function Register-UserPathDirectory {
    <#
    Put $Directory on the user's PATH permanently, and on this session's now.

    The value is read and written RAW, as REG_EXPAND_SZ.
    [Environment]::GetEnvironmentVariable expands %USERPROFILE%-style
    references and SetEnvironmentVariable writes REG_SZ, so round-tripping
    through them would silently freeze every such entry in the user's PATH.
    #>
    param([string]$Directory)
    $key = Get-Item -LiteralPath 'HKCU:\Environment'
    $current = $key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    $updated = Add-PathEntry $current $Directory
    if ($updated -ne $current) {
        New-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'Path' `
            -Value $updated -PropertyType ExpandString -Force | Out-Null
        # Explorer only rereads the environment when told to. Setting and
        # clearing a throwaway user variable through the .NET API broadcasts
        # WM_SETTINGCHANGE, so terminals opened from now on see the new entry
        # without logging off.
        [Environment]::SetEnvironmentVariable('DRERIO_LOGAI_PATH_REFRESH', '1', 'User')
        [Environment]::SetEnvironmentVariable('DRERIO_LOGAI_PATH_REFRESH', $null, 'User')
    }
    $env:Path = Add-PathEntry $env:Path $Directory
}

function Get-PythonCandidates {
    # The py launcher first: it is what python.org installs and it can select a
    # version explicitly. Then whatever `python` is, then the default per-user
    # install folders -- which is where winget puts Python, and which are not on
    # this session's PATH until the next terminal.
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'python'; Args = @() }
    )
    if ($env:LOCALAPPDATA) {
        foreach ($ver in @('312', '313')) {
            $candidates += @{
                Exe  = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver\python.exe")
                Args = @()
            }
        }
    }
    return $candidates
}

function Find-SupportedPython {
    <#
    Return @{ Version = '3.12'; Executable = 'C:\...\python.exe' } for the first
    interpreter in the supported range, or $null.

    The supported range is >=3.12,<3.14 (pyproject.toml). The ceiling is not
    conservatism: the pinned numpy publishes wheels only up to cp313, so on 3.14
    the install tries to compile numpy from source, fails, and leaves the project
    uninstalled -- a state that only announces itself one command later.
    #>

    # The probe prints an INTEGER (312, 313) on purpose. PowerShell strips
    # quotes when it hands arguments to a native executable, so the obvious
    # `print("%d.%d" % ...)` reaches python as `print(%d.%d % ...)` and dies
    # with a SyntaxError -- which this loop would read as "no Python here".
    # Keeping the snippet free of string literals sidesteps the quoting.
    $probe = 'import sys; print(sys.version_info[0]*100 + sys.version_info[1]); print(sys.executable)'

    foreach ($candidate in (Get-PythonCandidates)) {
        $exe = $candidate.Exe
        $pyArgs = $candidate.Args
        if (-not (Test-CommandExists $exe)) { continue }
        try {
            # 2>$null: `py -3.13` on a machine without it writes a multi-line
            # "No suitable Python runtime found" block that is noise here.
            $output = @(& $exe @pyArgs -c $probe 2>$null)
        }
        catch { continue }
        if ($LASTEXITCODE -ne 0 -or $output.Count -lt 2) { continue }

        try { $code = [int]$output[0] } catch { continue }
        $pretty = "$([math]::Floor($code / 100)).$($code % 100)"
        if ($code -in @(312, 313)) {
            Write-Host "  Using Python $pretty ($exe $($pyArgs -join ' '))"
            return @{ Version = $pretty; Executable = [string]$output[1] }
        }
        Write-Host "  Ignoring Python $pretty ($exe $($pyArgs -join ' ')) - outside the supported range"
    }
    return $null
}

function Install-PythonWithWinget {
    # --scope user: no administrator prompt. winget exits non-zero for benign
    # outcomes too ("already installed"), so the caller re-probes rather than
    # trusting the exit code.
    & winget install --id Python.Python.3.12 --exact --scope user --silent `
        --accept-package-agreements --accept-source-agreements | Out-Host
    Update-SessionPath
}

function Find-PoetryExecutable {
    <#
    Return the full path to poetry.exe, or $null.

    PATH first, then the folders Poetry's official installer uses. A Poetry
    that is installed but not on PATH is the common case on Windows -- its
    installer prints a request to edit PATH, and most people close the window
    without doing it.
    #>
    $onPath = Get-Command 'poetry' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($onPath) { return $onPath.Source }

    $candidates = @()
    if ($env:POETRY_HOME) { $candidates += (Join-Path $env:POETRY_HOME 'bin\poetry.exe') }
    if ($env:APPDATA) {
        $candidates += (Join-Path $env:APPDATA 'Python\Scripts\poetry.exe')
        $candidates += (Join-Path $env:APPDATA 'pypoetry\venv\Scripts\poetry.exe')
    }
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return $null
}

function Install-Poetry {
    param([string]$PythonExe)

    # Windows PowerShell 5.1 still negotiates TLS 1.0 by default on some builds,
    # which python-poetry.org refuses.
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    }
    catch { }

    $installer = Join-Path ([IO.Path]::GetTempPath()) 'drerio-logai-install-poetry.py'
    try {
        Invoke-WebRequest -Uri 'https://install.python-poetry.org' -UseBasicParsing -OutFile $installer
    }
    catch {
        Write-Host "  Could not download the Poetry installer: $($_.Exception.Message)"
        return $null
    }

    Write-Host '  (Poetry''s installer may ask you to add a folder to PATH. This script does that for you.)'
    & $PythonExe $installer | Out-Host
    $exitCode = $LASTEXITCODE
    Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue
    if ($exitCode -ne 0) { return $null }
    return Find-PoetryExecutable
}

# Dot-sourced (tests): stop here, having defined the helpers only.
if ($MyInvocation.InvocationName -eq '.') { return }

$TotalSteps = 4

# --------------------------------------------------------------------------
# 1. Python
# --------------------------------------------------------------------------
Write-Step 1 $TotalSteps 'Checking Python'

$python = Find-SupportedPython

if (-not $python -and (Test-CommandExists 'winget')) {
    Write-Host '  No supported Python (3.12 or 3.13) was found on this computer.'
    Write-Host '  Python is the engine DRerio LogAI runs on.'
    if (Confirm-Offer 'Install Python 3.12 now? (downloads from python.org through winget and accepts its license for you)') {
        Write-Host '  Installing Python 3.12 -- this takes a few minutes...'
        Install-PythonWithWinget
        $python = Find-SupportedPython
    }
}

if (-not $python) {
    Write-Problem @"
No supported Python found. DRerio LogAI needs Python 3.12 (3.13 also works;
3.14 does NOT).

Install it from:
    https://www.python.org/downloads/release/python-3129/

Download "Windows installer (64-bit)". On the FIRST screen of the installer,
tick "Add python.exe to PATH" before clicking Install.

Then close this window and double-click install.bat again.
"@
    exit 1
}

# --------------------------------------------------------------------------
# 2. Poetry
# --------------------------------------------------------------------------
Write-Step 2 $TotalSteps 'Checking Poetry'

$Poetry = Find-PoetryExecutable

if (-not $Poetry) {
    Write-Host '  Poetry is not installed. It is the tool that downloads the libraries'
    Write-Host '  DRerio LogAI needs.'
    if (Confirm-Offer 'Install Poetry now? (official installer from python-poetry.org)') {
        $Poetry = Install-Poetry -PythonExe $python.Executable
    }
}

if (-not $Poetry) {
    Write-Problem @"
Poetry is not installed. It is the tool that installs the application's
dependencies.

Run install.bat again and answer Y when it offers to install Poetry, or install
it by hand following https://python-poetry.org/docs/#installation
"@
    exit 1
}

if (-not (Test-CommandExists 'poetry')) {
    $poetryDir = Split-Path -Parent $Poetry
    Register-UserPathDirectory $poetryDir
    Write-Host "  Added $poetryDir to your PATH, so 'poetry' also works in terminal windows opened from now on."
}
Write-Host "  $(& $Poetry --version)"

# --------------------------------------------------------------------------
# 3. Dependencies
# --------------------------------------------------------------------------
Write-Step 3 $TotalSteps 'Installing dependencies (this takes several minutes)'

# Pin the environment to the interpreter validated above. Poetry otherwise
# builds it from whichever python it finds first, which on a machine with 3.14
# installed alongside is the one that breaks.
$pythonExe = $python.Executable
Write-Host "  Environment will use Python $($python.Version) at $pythonExe"

Push-Location $RepoRoot
try {
    & $Poetry env use $pythonExe
    if ($LASTEXITCODE -ne 0) { throw "poetry env use failed (exit $LASTEXITCODE)" }

    if ($Dev) { & $Poetry install --with dev } else { & $Poetry install }
    if ($LASTEXITCODE -ne 0) {
        Write-Problem @"
'poetry install' failed. Nothing here needs a C compiler -- every dependency
ships as a prebuilt wheel -- so the usual causes are a dropped network
connection or not enough free disk (the environment needs about 1.7 GB).

Fix the cause and run install.bat again; it resumes rather than starting over.
"@
        exit 1
    }

    # The install is only real if the package imports. Poetry reports success
    # for a run that resolved everything and still left the project itself
    # uninstalled, and that is precisely the state that surfaces later as
    # "No module named 'zebtrack'".
    & $Poetry run python -c "import zebtrack" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Problem @"
Dependencies installed, but the 'zebtrack' package itself did not. Check which
interpreter the environment was built on:

    poetry run python -V

It must report 3.12 or 3.13. If it does not, delete the .venv folder and run
install.bat again.
"@
        exit 1
    }
    Write-Host '  Dependencies installed.'

    if ($Dev) {
        & $Poetry run pre-commit install
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
        & $Poetry run fetch-weights
        if ($LASTEXITCODE -ne 0) {
            Write-Problem @"
The detector models were not downloaded. The application will start but cannot
track until they are present.

Run install.bat again, or from a terminal in this folder:
    poetry run fetch-weights

The download starts over but verifies every file against a recorded SHA-256,
so an interrupted attempt is discarded rather than half-kept.
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
