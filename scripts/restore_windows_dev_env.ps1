param(
    [switch]$DryRun,
    [switch]$ForceRecreateVenv,
    [switch]$KeepLegacyOpenVenv,
    [switch]$SkipExtensions,
    [switch]$SkipGitNormalization,
    [switch]$SkipPreCommit,
    [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-WarnLine {
    param([string]$Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
}

function Invoke-DryAction {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    if ($DryRun) {
        Write-Host "  [DRY-RUN] $Name" -ForegroundColor DarkYellow
        return
    }

    & $Action
    Write-Ok $Name
}

function Get-PoetryCommand {
    $poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
    if ($poetryCmd) {
        return "poetry"
    }

    $candidatePaths = @(
        "$env:APPDATA\Python\Scripts\poetry.exe",
        "$env:LOCALAPPDATA\Programs\Python\Scripts\poetry.exe",
        "$env:USERPROFILE\.local\bin\poetry.exe"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Install-PoetryIfMissing {
    $poetryCommand = Get-PoetryCommand
    if ($poetryCommand) {
        Write-Ok "Poetry encontrado: $poetryCommand"
        return $poetryCommand
    }

    Write-WarnLine "Poetry não encontrado no PATH. Instalando via instalador oficial..."

    if ($DryRun) {
        Write-Host "  [DRY-RUN] Install Poetry: (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -" -ForegroundColor DarkYellow
        return "poetry"
    }

    ((Invoke-WebRequest -Uri "https://install.python-poetry.org" -UseBasicParsing).Content | py -) 2>&1 | Out-Host

    $poetryCommand = Get-PoetryCommand
    if (-not $poetryCommand) {
        throw "Poetry foi instalado, mas não foi encontrado. Reabra o terminal e execute novamente."
    }

    Write-Ok "Poetry instalado: $poetryCommand"
    return $poetryCommand
}

function Set-WorkspaceInterpreterPath {
    param([string]$SettingsPath)

    if (-not (Test-Path $SettingsPath)) {
        throw "Arquivo .vscode/settings.json não encontrado em: $SettingsPath"
    }

    $raw = Get-Content -Path $SettingsPath -Raw -Encoding UTF8

    $updated = $raw -replace '"python.defaultInterpreterPath"\s*:\s*"[^"]*"', '"python.defaultInterpreterPath": ".venv\\Scripts\\python.exe"'

    if ($updated -notmatch '"terminal.integrated.env.windows"') {
        $terminalEnvSnippet = @'
,    "terminal.integrated.env.windows": {
        "VIRTUAL_ENV": "${workspaceFolder}\\.venv",
        "PATH": "${workspaceFolder}\\.venv\\Scripts;${env:PATH}"
    }
'@
        $updated = $updated -replace '"terminal.integrated.enablePersistentSessions"\s*:\s*false', '"terminal.integrated.enablePersistentSessions": false' + $terminalEnvSnippet
    }

    if ($updated -eq $raw) {
        Write-WarnLine "Nenhuma substituição foi feita em python.defaultInterpreterPath (chave não encontrada?)"
    }

    Set-Content -Path $SettingsPath -Value $updated -Encoding UTF8
}

function Install-RecommendedExtensions {
    param([string]$ExtensionsFile)

    $codeCmd = Get-Command code -ErrorAction SilentlyContinue
    if (-not $codeCmd) {
        Write-WarnLine "Comando 'code' não encontrado no PATH. Pulei instalação de extensões."
        return
    }

    if (-not (Test-Path $ExtensionsFile)) {
        Write-WarnLine "Arquivo de extensões não encontrado: $ExtensionsFile"
        return
    }

    $content = Get-Content -Path $ExtensionsFile -Raw -Encoding UTF8
    $json = $content | ConvertFrom-Json

    if (-not $json.recommendations) {
        Write-WarnLine "Nenhuma recomendação encontrada em $ExtensionsFile"
        return
    }

    foreach ($extensionId in $json.recommendations) {
        Invoke-DryAction -Name "Instalar extensão VS Code: $extensionId" -Action {
            code --install-extension $extensionId --force | Out-Null
        }
    }
}

Write-Step "Restaurando ambiente de desenvolvimento ZebTrack-AI (Windows)"

$repoRoot = Get-Location
Write-Host "  Diretório atual: $repoRoot"

Write-Step "Pré-checagens"
Invoke-DryAction -Name "Verificar git disponível" -Action {
    git --version | Out-Null
}
Invoke-DryAction -Name "Verificar python disponível" -Action {
    py --version | Out-Null
}

$poetry = Install-PoetryIfMissing

Invoke-DryAction -Name "Exibir versão do Poetry" -Action {
    & $poetry --version
}

Write-Step "Consolidação de ambientes Python"
if (-not $KeepLegacyOpenVenv) {
    Invoke-DryAction -Name "Remover ambiente legado openvino_env (se existir)" -Action {
        if (Test-Path ".\openvino_env") {
            Remove-Item -Path ".\openvino_env" -Recurse -Force
        }
    }
}
else {
    Write-WarnLine "Mantendo openvino_env por opção explícita (-KeepLegacyOpenVenv)."
}

if ($ForceRecreateVenv) {
    Invoke-DryAction -Name "Remover .venv para recriação limpa" -Action {
        if (Test-Path ".\.venv") {
            Remove-Item -Path ".\.venv" -Recurse -Force
        }
    }
}

Invoke-DryAction -Name "Configurar Poetry local para criar .venv no projeto" -Action {
    & $poetry config virtualenvs.create true --local
    & $poetry config virtualenvs.in-project true --local
}

Invoke-DryAction -Name "Instalar dependências com Poetry (runtime + dev)" -Action {
    & $poetry install --with dev --no-interaction
}

Write-Step "Hardening do VS Code"
Invoke-DryAction -Name "Ajustar python.defaultInterpreterPath para .venv relativo ao workspace" -Action {
    Set-WorkspaceInterpreterPath -SettingsPath ".\.vscode\settings.json"
}
Invoke-DryAction -Name "Desativar integração GK CLI (GitLens) no workspace" -Action {
    $settingsRaw = Get-Content -Path ".\.vscode\settings.json" -Raw -Encoding UTF8
    $settingsRaw = $settingsRaw -replace '"gitlens.gitkraken.cli.integration.enabled"\s*:\s*true', '"gitlens.gitkraken.cli.integration.enabled": false'
    if ($settingsRaw -notmatch '"gitlens.gitkraken.cli.insiders.enabled"') {
        $settingsRaw = $settingsRaw -replace '"gitlens.gitkraken.cli.integration.enabled"\s*:\s*false', '"gitlens.gitkraken.cli.integration.enabled": false,' + "`n" + '    "gitlens.gitkraken.cli.insiders.enabled": false'
    }
    Set-Content -Path ".\.vscode\settings.json" -Value $settingsRaw -Encoding UTF8
}

if (-not $SkipExtensions) {
    Invoke-DryAction -Name "Instalar extensões recomendadas do workspace" -Action {
        Install-RecommendedExtensions -ExtensionsFile ".\.vscode\extensions.json"
    }
}
else {
    Write-WarnLine "Pulando reinstalação de extensões por opção (-SkipExtensions)."
}

Write-Step "Normalização Git"
if (-not $SkipGitNormalization) {
    Invoke-DryAction -Name "Configurar safecrlf (global/local)" -Action {
        git config --global core.safecrlf warn
        git config --local core.safecrlf warn
    }
}
else {
    Write-WarnLine "Pulando normalização Git por opção (-SkipGitNormalization)."
}

Write-Step "Git hooks e validações"
if (-not $SkipPreCommit) {
    Invoke-DryAction -Name "Instalar hooks pre-commit" -Action {
        & $poetry run pre-commit install
    }
}
else {
    Write-WarnLine "Pulando instalação de pre-commit por opção (-SkipPreCommit)."
}

if (-not $SkipValidation) {
    Invoke-DryAction -Name "Smoke check: imports críticos" -Action {
        & $poetry run python -c "import cv2, torch, openvino, tkinter; print('imports-ok')"
    }
    Invoke-DryAction -Name "Smoke check: ruff" -Action {
        & $poetry run ruff --version
    }
    Invoke-DryAction -Name "Smoke check: pytest collection" -Action {
        & $poetry run pytest --collect-only -q
    }
}
else {
    Write-WarnLine "Pulando validações por opção (-SkipValidation)."
}

Write-Step "Resumo"
Write-Host "  - Reabra o VS Code após a execução para garantir seleção automática do interpretador."
Write-Host "  - Verifique se o canto inferior direito mostra: .venv (Python 3.12.x)."
Write-Host "  - Em terminal novo do VS Code, use: poetry run pytest -q"
Write-Ok "Restauração finalizada."
