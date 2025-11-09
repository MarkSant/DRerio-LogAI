# Agent Instructions - Phase 1, Group 2 (INDEPENDENTE)

**✅ Este grupo pode ser executado IMEDIATAMENTE em paralelo**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 1, Group 2
- **Número de Agentes**: 2 (podem trabalhar simultaneamente)
- **Dependências**: Nenhuma (independentes de P1-T5)
- **Bloqueia**: Ninguém
- **Branch**: `refactor/phase-1-critical-fixes`

---

## 🤖 AGENT-3: Settings Injection (P1-T3)

### 📌 Contexto
Você é o **Agent-3** responsável por eliminar imports singleton de `settings` e implementar injeção de dependência em toda a aplicação.

### 🎯 Objetivo
Substituir todos os `from zebtrack import settings` por injeção de `settings_obj` via construtor, garantindo testabilidade e isolamento.

### 📂 Acesso ao Repositório
```bash
# Clone o repositório
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Crie e faça checkout da branch de trabalho
git checkout -b refactor/phase-1-critical-fixes

# Configure o ambiente
poetry install
poetry shell
```

### 📖 Documentação Detalhada
Leia cuidadosamente:

1. **PLANO_REFATORACAO_PARALELA_PARTE1.md**
   - Seção: "P1-T3: Settings Injection (Agent-3)"
   - Linhas: ~400-500

2. **docs/DEPENDENCY_INJECTION_GUIDE.md**
   - Padrões de injeção
   - Exemplos completos

3. **AGENT_ORCHESTRATION_GUIDE.md**
   - Seção: "Agent-3: Settings Injection (P1-T3)"

### 🛠️ Implementação Passo a Passo

#### Passo 1: Identificar Imports Singleton
```bash
# Encontre todos os imports de settings
grep -r "from zebtrack import settings" src/ --include="*.py"

# Arquivo principal: src/zebtrack/io/live_camera.py
```

#### Passo 2: Refatorar LiveCameraService
Edite `src/zebtrack/io/live_camera.py`:

**ANTES:**
```python
from zebtrack import settings

class LiveCameraService:
    def __init__(self, camera_id: int = 0):
        self.camera_id = camera_id
        self.backend = settings.camera.backend
```

**DEPOIS:**
```python
from zebtrack.settings import Settings

class LiveCameraService:
    def __init__(self, settings_obj: Settings, camera_id: int = 0):
        self._settings = settings_obj
        self.camera_id = camera_id
        self.backend = self._settings.camera.backend
```

#### Passo 3: Atualizar Composition Root
Edite `src/zebtrack/__main__.py` (linhas ~200-220):

**ANTES:**
```python
live_camera_service = LiveCameraService()
```

**DEPOIS:**
```python
live_camera_service = LiveCameraService(settings_obj=settings_obj)
```

#### Passo 4: Criar/Atualizar Testes
Crie `tests/test_settings_injection.py`:

```python
"""Test settings injection in services."""

import pytest
from zebtrack.settings import Settings
from zebtrack.io.live_camera import LiveCameraService


def test_live_camera_service_requires_settings():
    """LiveCameraService requires settings_obj parameter."""
    settings = Settings()

    # Should work with settings
    service = LiveCameraService(settings_obj=settings, camera_id=0)
    assert service._settings is settings


def test_live_camera_service_uses_injected_settings():
    """LiveCameraService uses injected settings, not singleton."""
    settings1 = Settings()
    settings1.camera.backend = "DSHOW"

    settings2 = Settings()
    settings2.camera.backend = "MSMF"

    service1 = LiveCameraService(settings_obj=settings1)
    service2 = LiveCameraService(settings_obj=settings2)

    assert service1.backend == "DSHOW"
    assert service2.backend == "MSMF"
```

#### Passo 5: Validar Implementação
```bash
# Execute testes específicos
poetry run pytest tests/test_settings_injection.py -v

# Execute suite completa de testes rápidos
poetry run pytest -q -m "not gui and not slow"

# Verifique que nenhum teste quebrou
```

#### Passo 6: Verificar Linting
```bash
# Verifique estilo
poetry run ruff check src/zebtrack/io/live_camera.py src/zebtrack/__main__.py tests/test_settings_injection.py

# Formate código
poetry run ruff format src/zebtrack/io/live_camera.py src/zebtrack/__main__.py tests/test_settings_injection.py
```

#### Passo 7: Commit e Push
```bash
# Adicione arquivos modificados
git add src/zebtrack/io/live_camera.py src/zebtrack/__main__.py tests/test_settings_injection.py

# Commit
git commit -m "refactor(di): Implement settings injection in LiveCameraService (P1-T3)

- Replace singleton import with constructor injection
- Add settings_obj parameter to LiveCameraService
- Update Composition Root in __main__.py
- Add unit tests for settings injection
- Improve testability and isolation

Task: P1-T3
Agent: Agent-3"

# Push
git push origin refactor/phase-1-critical-fixes
```

### ✅ Critérios de Sucesso
- [ ] Todos os `from zebtrack import settings` removidos
- [ ] Todos os serviços recebem `settings_obj` via construtor
- [ ] Composition Root (`__main__.py`) atualizado
- [ ] Testes passando (mínimo 2 novos testes)
- [ ] Zero erros Ruff
- [ ] Código formatado
- [ ] Commit e push concluídos

### ⏱️ Estimativa
**Total**: ~90 minutos

---

## 🤖 AGENT-4: CI/CD Fixes (P1-T4)

### 📌 Contexto
Você é o **Agent-4** responsável por corrigir problemas de CI/CD no GitHub Actions, especificamente timeouts em testes GUI e configuração de cache.

### 🎯 Objetivo
Configurar pytest-timeout, otimizar cache Poetry, e garantir que pipeline CI execute em <10 minutos com 100% de aprovação.

### 📂 Acesso ao Repositório
```bash
# Clone o repositório
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Crie e faça checkout da branch de trabalho
git checkout -b refactor/phase-1-critical-fixes

# Configure o ambiente
poetry install
poetry shell
```

### 📖 Documentação Detalhada
Leia cuidadosamente:

1. **PLANO_REFATORACAO_PARALELA_PARTE1.md**
   - Seção: "P1-T4: CI/CD Fixes (Agent-4)"
   - Linhas: ~500-600

2. **AGENT_ORCHESTRATION_GUIDE.md**
   - Seção: "Agent-4: CI/CD Fixes (P1-T4)"

### 🛠️ Implementação Passo a Passo

#### Passo 1: Atualizar pyproject.toml
Edite `pyproject.toml` - adicione `pytest-timeout`:

```toml
[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-cov = "^5.0.0"
pytest-xdist = "^3.5.0"
pytest-timeout = "^2.2.0"  # ADICIONE ESTA LINHA
```

#### Passo 2: Configurar pytest-timeout
Edite `pytest.ini`:

```ini
[pytest]
# ... configurações existentes ...

# Timeout configuration (prevent hanging tests)
timeout = 300
timeout_method = thread
```

#### Passo 3: Atualizar GitHub Actions Workflow
Edite `.github/workflows/ci.yml`:

**SEÇÃO 1: Cache Otimizado**
```yaml
- name: Cache Poetry dependencies
  uses: actions/cache@v4
  with:
    path: |
      ~/.cache/pypoetry
      .venv
    key: ${{ runner.os }}-poetry-${{ hashFiles('**/poetry.lock') }}
    restore-keys: |
      ${{ runner.os }}-poetry-
```

**SEÇÃO 2: Testes com Timeout**
```yaml
- name: Run fast tests
  run: |
    poetry run pytest -q -m "not gui and not slow" --timeout=60
  timeout-minutes: 5

- name: Run GUI tests (sequential)
  run: |
    poetry run pytest -m gui -n0 --timeout=300
  timeout-minutes: 15
```

**SEÇÃO 3: Timeout Global**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 30  # ADICIONE ESTA LINHA
```

#### Passo 4: Testar Localmente
```bash
# Instale pytest-timeout
poetry add --group dev pytest-timeout

# Execute testes com timeout
poetry run pytest -q --timeout=60

# Simule timeout (deve falhar após 5s)
poetry run pytest tests/test_timeout.py --timeout=5
```

#### Passo 5: Criar Teste de Validação
Crie `tests/test_ci_configuration.py`:

```python
"""Test CI/CD configuration."""

import pytest
import time


def test_timeout_configuration():
    """Pytest timeout is configured and working."""
    # This test should pass quickly
    assert True


@pytest.mark.slow
def test_slow_test_with_timeout():
    """Slow tests respect timeout configuration."""
    # Sleep for 2 seconds (should pass with 300s timeout)
    time.sleep(2)
    assert True


def test_fast_test_performance():
    """Fast tests complete quickly."""
    # Should complete in <1 second
    start = time.time()
    result = sum(range(1000))
    elapsed = time.time() - start

    assert result > 0
    assert elapsed < 1.0  # Less than 1 second
```

#### Passo 6: Validar CI Localmente
```bash
# Execute testes como CI faria
poetry run pytest -q -m "not gui and not slow" --timeout=60

# Verifique que completa em <5 minutos
```

#### Passo 7: Commit e Push
```bash
# Adicione arquivos
git add pyproject.toml pytest.ini .github/workflows/ci.yml tests/test_ci_configuration.py

# Commit
git commit -m "ci: Configure pytest-timeout and optimize CI pipeline (P1-T4)

- Add pytest-timeout plugin (300s default, 60s for fast tests)
- Optimize Poetry cache in GitHub Actions
- Add timeout-minutes to jobs and steps
- Create CI configuration validation tests
- Target: <10 minute CI execution

Task: P1-T4
Agent: Agent-4"

# Push e monitore CI
git push origin refactor/phase-1-critical-fixes
```

#### Passo 8: Monitorar GitHub Actions
```bash
# Abra o navegador e verifique:
# https://github.com/MarkSant/ZebTrack-AI/actions

# Aguarde CI completar e verifique:
# - Todos os testes passam ✅
# - Tempo total < 10 minutos ✅
# - Cache funcionando ✅
```

### ✅ Critérios de Sucesso
- [ ] `pytest-timeout` adicionado ao `pyproject.toml`
- [ ] `pytest.ini` configurado com timeout=300
- [ ] GitHub Actions atualizado com cache otimizado
- [ ] Timeouts configurados em jobs e steps
- [ ] Testes de validação CI criados
- [ ] CI completa em <10 minutos
- [ ] 100% de testes passando no CI
- [ ] Zero erros Ruff
- [ ] Commit e push concluídos

### 🚨 Troubleshooting

**Problema**: Cache não está funcionando
```yaml
# Solução: Verifique que key usa hashFiles correto
key: ${{ runner.os }}-poetry-${{ hashFiles('**/poetry.lock') }}
```

**Problema**: Testes ainda dando timeout
```bash
# Solução: Aumente timeout para testes específicos
poetry run pytest tests/test_slow.py --timeout=600
```

### ⏱️ Estimativa
**Total**: ~60 minutos

---

## 📊 Resumo do Grupo 2

### Execução Paralela
Os dois agentes (Agent-3 e Agent-4) podem trabalhar **simultaneamente** pois:
- ✅ Modificam arquivos diferentes
- ✅ Sem dependências entre si
- ✅ Sem dependência de P1-T5

### Ordem Recomendada de Commits
1. Agent-3 faz commit primeiro (modifica código core)
2. Agent-4 faz commit depois (modifica CI/infra)

### Comunicação de Conclusão do Grupo
Após ambos completarem:

```
✅ GRUPO 2 CONCLUÍDO (Phase 1)

Tarefas Concluídas:
- ✅ Agent-3 (P1-T3): Settings Injection
- ✅ Agent-4 (P1-T4): CI/CD Fixes

Commits:
- Agent-3: [hash]
- Agent-4: [hash]

Branch: refactor/phase-1-critical-fixes

Próximo Passo:
Aguardar conclusão de Agent-5 (P1-T5) para desbloquear Grupo 3
```

---

**Data de Execução**: ___________
**Agents Responsáveis**: ___________
**Status Grupo**: [ ] Não Iniciado | [ ] Em Progresso | [ ] Concluído
