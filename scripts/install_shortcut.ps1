<#
.SYNOPSIS
    Creates the "DRerio LogAI" desktop and Start Menu shortcuts.

.DESCRIPTION
    A researcher operating the software should not have to open a terminal and
    remember an activation command to start it. This writes a normal Windows
    shortcut that launches the app in its Poetry environment on a double-click.

    The shortcut targets `.venv\Scripts\pythonw.exe -m zebtrack`, and each half
    of that is deliberate:

      * pythonw.exe, not python.exe, so no console window sits behind the GUI.
        Closing that window would kill a running analysis, and it shows the
        operator nothing they can act on -- the same records go to
        logs\analysis.log either way.

      * -m zebtrack, not the `zebtrack` console script, because Poetry
        generates that script as a .cmd wrapper (there is no zebtrack.exe) and
        a .cmd target reintroduces the console window that pythonw avoids.

    Run it from anywhere; paths are resolved from this file's location.

.PARAMETER NoDesktop
    Skip the desktop shortcut; create only the Start Menu entry.

.PARAMETER Remove
    Delete the shortcuts instead of creating them.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoDesktop,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

$ShortcutName = 'DRerio LogAI.lnk'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-ShortcutTargets {
    $desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) $ShortcutName
    $startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) $ShortcutName
    if ($NoDesktop) { return @($startMenu) }
    return @($desktop, $startMenu)
}

if ($Remove) {
    foreach ($path in Get-ShortcutTargets) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
            Write-Host "Removed $path"
        }
    }
    return
}

# The interpreter must exist: a shortcut to a missing target fails on
# double-click with a dialog that names neither the cause nor the fix.
$Pythonw = Join-Path $RepoRoot '.venv\Scripts\pythonw.exe'
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
foreach ($exe in @($Pythonw, $Python)) {
    if (-not (Test-Path -LiteralPath $exe)) {
        throw @"
No virtual environment found at:
    $exe

Run 'poetry install' in $RepoRoot first, then run this script again.
"@
    }
}

# Fail early rather than write a shortcut that opens and immediately dies.
#
# Verified through python.exe even though the shortcut targets pythonw.exe:
# pythonw is a GUI-subsystem binary, so PowerShell does not wait for it and
# leaves $LASTEXITCODE unset -- a check against it reads as failure no matter
# what the interpreter did. Both executables share the environment, so the
# console one answers the same question and answers it reliably.
& $Python -c "import zebtrack" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw @"
The environment at $RepoRoot\.venv cannot import 'zebtrack'.

That usually means 'poetry install' did not finish installing the project --
most often because the environment was built on an unsupported Python. Check
with 'poetry run python -V' (3.12 or 3.13), then re-run 'poetry install'.
"@
}

$IconPath = Join-Path $RepoRoot 'src\zebtrack\ui\assets\drerio_logai.ico'
if (-not (Test-Path -LiteralPath $IconPath)) {
    Write-Warning "Icon not found at $IconPath; the shortcut will use the default Python icon."
    $IconPath = $Pythonw
}

$shell = New-Object -ComObject WScript.Shell
try {
    foreach ($path in Get-ShortcutTargets) {
        $parent = Split-Path -Parent $path
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }

        # CreateShortcut overwrites an existing .lnk, which is what we want:
        # re-running after the repository moved must repair the target rather
        # than leave a shortcut pointing at a path that no longer exists.
        $lnk = $shell.CreateShortcut($path)
        $lnk.TargetPath = $Pythonw
        $lnk.Arguments = '-m zebtrack'
        # Not strictly required -- zebtrack.paths anchors config and weights to
        # the repository root regardless of where it is launched from -- but it
        # keeps any relative path a user types in a dialog anchored sensibly.
        $lnk.WorkingDirectory = $RepoRoot
        $lnk.IconLocation = $IconPath
        $lnk.Description = 'DRerio LogAI - zebrafish tracking and behavioral analysis'
        $lnk.Save()

        Write-Host "Shortcut created: $path"
    }
}
finally {
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
}
