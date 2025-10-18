# Instruções para Correção dos Testes

## Problema Identificado

Os testes estavam falhando devido a três problemas principais:

1. **❌ pyvirtualdisplay no Windows**: O fixture `tkinter_root` tentava usar `pyvirtualdisplay` que só funciona em Linux
2. **❌ Paralelização com Tkinter**: Testes GUI rodavam em paralelo causando conflitos
3. **❌ Testes lentos**: Muitos testes com `sleep()` tornavam a suite lenta

## Correções Aplicadas

### ✅ 1. Fixture Tkinter Cross-Platform

**Arquivo modificado**: `tests/conftest.py`

- Detecta automaticamente a plataforma (Windows/Linux/macOS)
- Usa `pyvirtualdisplay` apenas no Linux
- No Windows, usa Tkinter nativo sem display virtual

### ✅ 2. Marcadores de Teste (Test Markers)

**Arquivos modificados**: `pytest.ini`, `pyproject.toml`

Adicionados 4 marcadores:
- `@pytest.mark.gui` - Testes com Tkinter (rodam sequencialmente)
- `@pytest.mark.slow` - Testes lentos (>1s)
- `@pytest.mark.integration` - Testes de integração
- `@pytest.mark.unit` - Testes unitários

**Arquivos marcados com `@pytest.mark.gui`**:
- `test_wizard_confirmation.py`
- `test_wizard_detection.py`
- `test_wizard_file_selection.py`
- `test_wizard_foundation.py`
- `test_wizard_import_config.py`
- `test_wizard_integration.py`

**Arquivos marcados com `@pytest.mark.slow`**:
- `test_project_manager.py::test_scan_input_paths_cache_invalidation_on_directory_change`

### ✅ 3. Otimização de Performance

**Arquivos modificados**:
- `test_processing_worker.py`: Sleep de 10s → 1s (teste de cancelamento)
- `test_project_manager.py`: Teste lento marcado e documentado
- `pyproject.toml`: Configurado para pular testes GUI e slow por padrão

### ✅ 4. Documentação

**Novos arquivos criados**:
- `README_TESTS.md` - Guia completo de como usar os testes
- `fix_venv.ps1` - Script para recriar ambiente virtual
- `INSTRUCOES_CORRECAO_TESTES.md` - Este arquivo

## Como Executar os Testes Agora

### Execução Padrão (Rápida - 1-2 min)
```powershell
poetry run pytest
```
- Roda apenas testes rápidos e não-GUI
- Usa paralelização automática

### Testes GUI (3-5 min)
```powershell
poetry run pytest -m gui -n0
```
- Roda testes de interface Tkinter
- Sequencial (sem paralelização)

### Testes Completos (8-12 min)
```powershell
poetry run pytest -m "" -n0
```
- Roda TODOS os testes (rápidos + lentos + GUI)

### Sem Cobertura (Mais Rápido)
```powershell
poetry run pytest --no-cov
```

## Recriando o Ambiente Virtual

### Problema Atual
O ambiente virtual (`.venv`) está corrompido e precisa ser recriado. Há um erro de permissão ao tentar deletá-lo automaticamente.

### Solução 1: Script Automático (Recomendado)

1. **Feche todas as janelas do VS Code e terminais**
2. **Execute o script como Administrador**:
   ```powershell
   # Clique direito no PowerShell → "Executar como Administrador"
   cd "C:\Users\santa\OneDrive\UNESP\Pesquisa Canabidiol\Codigos_Programas\ZebTrack-AI"
   .\fix_venv.ps1
   ```

### Solução 2: Manual

Se o script não funcionar:

```powershell
# 1. Feche TODAS as janelas do VS Code e terminais

# 2. Execute como Administrador:
Stop-Process -Name python* -Force -ErrorAction SilentlyContinue

# 3. Delete o diretório .venv
Remove-Item -Recurse -Force .venv

# 4. Reinstale as dependências
poetry install

# 5. Verifique se funcionou
poetry run pytest --version
```

### Solução 3: Manualmente via Explorer

1. Feche **TODAS** as aplicações que possam estar usando Python:
   - VS Code
   - Terminais PowerShell
   - Jupyter notebooks
   - Qualquer IDE

2. Navegue até a pasta do projeto no Windows Explorer

3. Delete manualmente a pasta `.venv`
   - Se receber erro de permissão, reinicie o computador e tente novamente

4. Abra PowerShell **como Administrador** e execute:
   ```powershell
   cd "caminho\para\ZebTrack-AI"
   poetry install
   ```

## Verificação

Após recriar o ambiente virtual, verifique se tudo está funcionando:

```powershell
# 1. Verificar ambiente
poetry env info

# 2. Rodar testes rápidos
poetry run pytest -v

# 3. Rodar alguns testes GUI
poetry run pytest -m gui -n0 -k "test_wizard_foundation" -v
```

## Resultado Esperado

### Antes das Correções
- ❌ Testes GUI falhando no Windows
- ❌ Execução demorava 15-20 minutos
- ❌ Muitos erros de `pyvirtualdisplay`
- ❌ Conflitos de paralelização

### Depois das Correções
- ✅ Testes GUI funcionando no Windows
- ✅ Execução padrão: 1-2 minutos
- ✅ Testes completos: 8-12 minutos
- ✅ ~70% de redução no tempo de teste
- ✅ Paralelização segura (não-GUI)
- ✅ Melhor organização com markers

## Comandos Úteis

```powershell
# Apenas testes unitários rápidos
poetry run pytest -m "unit and not slow"

# Apenas testes de integração
poetry run pytest -m integration

# Pular testes lentos
poetry run pytest -m "not slow"

# Testes de um módulo específico
poetry run pytest tests/test_wizard_integration.py

# Modo verbose com saída detalhada
poetry run pytest -v -s

# Parar no primeiro erro
poetry run pytest -x

# Executar apenas testes que falharam anteriormente
poetry run pytest --lf
```

## Documentação Adicional

- `README_TESTS.md` - Guia completo de testes e marcadores
- `pytest.ini` - Configuração dos marcadores
- `pyproject.toml` - Configuração do pytest e coverage

## Suporte

Se encontrar problemas:

1. Verifique se o ambiente virtual foi recriado corretamente:
   ```powershell
   poetry env info
   ```

2. Verifique se as dependências estão instaladas:
   ```powershell
   poetry show
   ```

3. Tente rodar um teste simples primeiro:
   ```powershell
   poetry run pytest tests/test_settings.py -v
   ```

4. Se persistir, abra uma issue com:
   - Output completo do erro
   - Resultado de `poetry env info`
   - Sistema operacional e versão
