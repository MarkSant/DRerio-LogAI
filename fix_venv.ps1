# Script PowerShell para recriar o ambiente virtual
# Execute como Administrador se encontrar erros de permissão

Write-Host "=== Limpeza do Ambiente Virtual ZebTrack-AI ===" -ForegroundColor Cyan
Write-Host ""

# Fechar processos Python que possam estar usando o .venv
Write-Host "1. Fechando processos Python..." -ForegroundColor Yellow
Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Remover diretório .venv
Write-Host "2. Removendo diretório .venv..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    try {
        Remove-Item -Recurse -Force .venv -ErrorAction Stop
        Write-Host "   ✓ Diretório .venv removido com sucesso" -ForegroundColor Green
    }
    catch {
        Write-Host "   ✗ Erro ao remover .venv: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "   Tente fechar todas as janelas do VS Code e terminais" -ForegroundColor Yellow
        Write-Host "   Depois execute este script novamente como Administrador" -ForegroundColor Yellow
        Read-Host "Pressione Enter para sair"
        exit 1
    }
}
else {
    Write-Host "   ℹ Diretório .venv não encontrado" -ForegroundColor Gray
}

# Limpar cache do Poetry
Write-Host "3. Limpando cache do Poetry..." -ForegroundColor Yellow
poetry cache clear pypi --all -n 2>$null

# Reinstalar dependências
Write-Host "4. Reinstalando dependências (isso pode demorar alguns minutos)..." -ForegroundColor Yellow
poetry install

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== ✓ Ambiente virtual recriado com sucesso! ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Próximos passos:" -ForegroundColor Cyan
    Write-Host "  1. Execute os testes: poetry run pytest" -ForegroundColor White
    Write-Host "  2. Ou apenas testes rápidos: poetry run pytest -m 'not slow'" -ForegroundColor White
    Write-Host ""
}
else {
    Write-Host ""
    Write-Host "=== ✗ Erro durante reinstalação ===" -ForegroundColor Red
    Write-Host "Verifique as mensagens de erro acima" -ForegroundColor Yellow
}

Read-Host "Pressione Enter para sair"
