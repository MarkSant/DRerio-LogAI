# Guia de Orquestração de Agentes - ZebTrack-AI Refactoring

## 🎯 Visão Geral

Este guia fornece os comandos exatos e instruções de coordenação para **15 agentes independentes** executarem o plano de refatoração paralela em **4 fases** ao longo de **7 semanas**.

## 📂 Arquivos de Referência

### Planos Detalhados

Os agentes devem consultar os seguintes arquivos para instruções completas:

```text
PLANO_REFATORACAO_PARALELA_PARTE1.md  (Fase 1: Correções Críticas)
PLANO_REFATORACAO_PARALELA_PARTE2.md  (Fases 2-4: God Objects, Testes, Documentação)
```

### Comandos de Acesso aos Planos

```bash
# Ler plano completo Fase 1
cat PLANO_REFATORACAO_PARALELA_PARTE1.md

# Ler plano completo Fases 2-4
cat PLANO_REFATORACAO_PARALELA_PARTE2.md

# Buscar tarefa específica (exemplo: P1-T1)
grep -A 100 "TAREFA P1-T1" PLANO_REFATORACAO_PARALELA_PARTE1.md

# Buscar tarefa específica (exemplo: P2-T1)
grep -A 100 "TAREFA P2-T1" PLANO_REFATORACAO_PARALELA_PARTE2.md
```

---

## 🚀 FASE 1: CORREÇÕES CRÍTICAS (Semanas 1-2)

**Objetivo**: Corrigir problemas críticos de arquitetura (exceções, recursos, settings, CI)

**Branch Base**: `refactor/phase-1-critical-fixes` (criar a partir de `main`)

**Coordenador**: Tech Lead

### ⚡ Grupo Paralelo 1A (PRIORITÁRIO - Executar PRIMEIRO)

**Tarefa Bloqueante**: Esta tarefa deve ser concluída ANTES de todas as outras da Fase 1

#### Agent-5: Custom Exception Hierarchy

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE1.md` → Seção "TAREFA P1-T5"

**Comandos de Início**:

```bash
# 1. Clonar repositório
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# 2. Instalar dependências
poetry install

# 3. Ler instruções da tarefa
grep -A 200 "TAREFA P1-T5: Custom Exception Hierarchy" PLANO_REFATORACAO_PARALELA_PARTE1.md

# 4. Criar branch
git checkout -b task/p1-t5-custom-exceptions

# 5. Implementar conforme instruções no plano
# ... (seguir Passos 1-4 do PLANO_REFATORACAO_PARALELA_PARTE1.md)

# 6. Executar testes
poetry run pytest tests/test_exceptions.py -v
poetry run pytest -q

# 7. Validar linting
poetry run ruff check .

# 8. Commit e push
git add src/zebtrack/exceptions.py tests/test_exceptions.py src/zebtrack/__init__.py
git commit -m "feat(p1-t5): Add comprehensive custom exception hierarchy

- Created 15+ custom exception classes
- Organized in domain-based hierarchy
- Added tests for all exception types
- Updated __init__.py exports

Refs: #phase-1"

git push origin task/p1-t5-custom-exceptions

# 9. Criar PR para branch de fase
gh pr create \
  --base refactor/phase-1-critical-fixes \
  --head task/p1-t5-custom-exceptions \
  --title "Phase 1 Task 5: Custom Exception Hierarchy" \
  --body "Implements comprehensive exception hierarchy as foundation for Phase 1 tasks.

**Changes:**
- ✅ 15+ custom exceptions created
- ✅ Hierarchical organization (ZebTrackError base)
- ✅ Domain-specific exceptions (IO, Detection, UI, etc)
- ✅ Full test coverage
- ✅ Zero Ruff errors

**Dependencies:**
- None (foundational task)

**Blockers:**
- P1-T1, P1-T2 depend on this merge

**Validation:**
\`\`\`bash
poetry run pytest tests/test_exceptions.py -v
poetry run ruff check .
\`\`\`"
```

**⏰ Tempo Estimado**: 2 dias

**🚦 Status**: Deve ser MERGEADO antes que Grupo 1B inicie

---

### ⚡ Grupo Paralelo 1B (Após P1-T5 mergeado)

**Pré-requisito**: PR de P1-T5 deve estar mergeado em `refactor/phase-1-critical-fixes`

Estes 2 agentes podem trabalhar **simultaneamente** após P1-T5:

#### Agent-1: Broad Exception Handling

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE1.md` → Seção "TAREFA P1-T1"

**Comandos de Início**:

```bash
# 1. Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install

# 2. Atualizar com latest da fase (INCLUINDO P1-T5 mergeado)
git checkout refactor/phase-1-critical-fixes
git pull origin refactor/phase-1-critical-fixes

# 3. Ler instruções
grep -A 300 "TAREFA P1-T1: Broad Exception Handling" PLANO_REFATORACAO_PARALELA_PARTE1.md

# 4. Criar branch
git checkout -b task/p1-t1-exception-handling

# 5. Identificar ocorrências
grep -r "except Exception:" src/ --include="*.py" > exceptions_to_fix.txt
cat exceptions_to_fix.txt
# Deve mostrar ~30 ocorrências

# 6. Implementar conforme Passos 1-5 do plano
# Substituir cada "except Exception:" por exceção específica

# 7. Validar
poetry run pytest -q
grep -r "except Exception:" src/ --include="*.py" | wc -l
# Deve retornar 0

# 8. Commit e PR
git add .
git commit -m "feat(p1-t1): Replace broad exception handlers with specific exceptions

- Replaced 30+ occurrences of 'except Exception:'
- Used custom exception hierarchy from P1-T5
- Added context to exception handling
- Maintained backward compatibility

Files modified:
- src/zebtrack/io/video_source.py
- src/zebtrack/io/recorder.py
- src/zebtrack/core/detector_service.py
- (... list all modified files)

Refs: #phase-1"

git push origin task/p1-t1-exception-handling

gh pr create \
  --base refactor/phase-1-critical-fixes \
  --head task/p1-t1-exception-handling \
  --title "Phase 1 Task 1: Replace Broad Exception Handling" \
  --body "..."
```

**⏰ Tempo Estimado**: 3 dias

---

#### Agent-2: Resource Management (Context Managers)

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE1.md` → Seção "TAREFA P1-T2"

**Comandos de Início**:

```bash
# 1-3. Setup (igual ao Agent-1)
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout refactor/phase-1-critical-fixes
git pull origin refactor/phase-1-critical-fixes

# 4. Ler instruções
grep -A 250 "TAREFA P1-T2: Resource Management" PLANO_REFATORACAO_PARALELA_PARTE1.md

# 5. Criar branch
git checkout -b task/p1-t2-resource-management

# 6. Implementar context managers conforme Passos 1-4
# Modificar Camera e Recorder classes

# 7. Testar
poetry run pytest tests/io/test_camera.py -v -k "context"
poetry run pytest tests/io/test_recorder.py -v -k "context"
poetry run pytest -q

# 8. Commit e PR
git add src/zebtrack/io/camera.py src/zebtrack/io/recorder.py tests/
git commit -m "feat(p1-t2): Add context managers for resource cleanup

- Implemented __enter__/__exit__ for Camera class
- Implemented __enter__/__exit__ for Recorder class  
- Updated usage patterns across codebase
- Added comprehensive tests for context manager behavior
- Ensures resources always cleaned up, even on exceptions

Refs: #phase-1"

git push origin task/p1-t2-resource-management

gh pr create \
  --base refactor/phase-1-critical-fixes \
  --head task/p1-t2-resource-management \
  --title "Phase 1 Task 2: Resource Management with Context Managers" \
  --body "..."
```

**⏰ Tempo Estimado**: 3 dias

---

### ⚡ Grupo Paralelo 1C (Independentes)

Estes 2 agentes podem trabalhar **simultaneamente** e **independentemente** de P1-T5:

#### Agent-3: Settings Injection Completion

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE1.md` → Seção "TAREFA P1-T3"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install

# Ler instruções
grep -A 200 "TAREFA P1-T3: Settings Injection" PLANO_REFATORACAO_PARALELA_PARTE1.md

# Criar branch DIRETAMENTE da main (não depende de P1-T5)
git checkout main
git checkout -b task/p1-t3-settings-injection

# Validar arquivos que ainda usam singleton
grep -r "from zebtrack import settings" src/zebtrack/
# Deve mostrar:
# src/zebtrack/ui/wizard/camera_step.py
# src/zebtrack/ui/wizard/arena_step.py

# Implementar conforme Passos 1-4

# Validar que singleton foi eliminado
grep -r "from zebtrack import settings" src/zebtrack/
# Deve retornar ZERO resultados

# Testar
poetry run pytest tests/ui/wizard/ -v
poetry run pytest -q

# Commit e PR
git commit -m "feat(p1-t3): Complete settings injection migration

- Converted camera_step.py to use settings_obj parameter
- Converted arena_step.py to use settings_obj parameter
- Updated WizardDialog to pass settings_obj
- Eliminated all singleton settings imports
- 100% dependency injection achieved

Refs: #phase-1"

git push origin task/p1-t3-settings-injection

gh pr create \
  --base refactor/phase-1-critical-fixes \
  --head task/p1-t3-settings-injection \
  --title "Phase 1 Task 3: Complete Settings Injection Migration" \
  --body "..."
```

**⏰ Tempo Estimado**: 2 dias

---

#### Agent-4: CI YAML Fixes

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE1.md` → Seção "TAREFA P1-T4"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI

# Ler instruções
grep -A 100 "TAREFA P1-T4: CI Fixes" PLANO_REFATORACAO_PARALELA_PARTE1.md

# Criar branch DIRETAMENTE da main
git checkout main
git checkout -b task/p1-t4-ci-fixes

# Ver erro atual
cat .github/workflows/ci.yml | sed -n '80,90p'

# Corrigir conforme Passos 1-3
# Linha 86: remover espaço após '-'

# Validar YAML
poetry run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"

# Commit e PR
git add .github/workflows/ci.yml
git commit -m "fix(p1-t4): Fix YAML syntax error in CI workflow

- Removed trailing space after '-' on line 86
- Validated YAML syntax
- CI should now pass without syntax errors

Refs: #phase-1"

git push origin task/p1-t4-ci-fixes

gh pr create \
  --base refactor/phase-1-critical-fixes \
  --head task/p1-t4-ci-fixes \
  --title "Phase 1 Task 4: Fix CI YAML Syntax Error" \
  --body "..."
```

**⏰ Tempo Estimado**: 1 dia

---

### 📋 Ordem de Merge - Fase 1

**CRÍTICO**: Seguir esta ordem exata para evitar conflitos:

```text
1. ✅ P1-T5 (Custom Exceptions)       → Merge PRIMEIRO
2. ✅ P1-T4 (CI Fixes)                → Merge em paralelo com P1-T3
3. ✅ P1-T3 (Settings Injection)      → Merge em paralelo com P1-T4
4. ✅ P1-T1 (Exception Handling)      → Merge APÓS P1-T5 (depende de exceções)
5. ✅ P1-T2 (Resource Management)     → Merge APÓS P1-T5 (depende de exceções)
6. ✅ Merge refactor/phase-1-critical-fixes → main
```

**Comandos de Merge (Coordenador)**:

```bash
# Após todas as 5 tarefas mergeadas na branch de fase
git checkout main
git pull origin main
git merge refactor/phase-1-critical-fixes --squash
git commit -m "feat: Complete Phase 1 refactoring - Critical Fixes

Phase 1 deliverables:
- ✅ Custom exception hierarchy (15+ exceptions)
- ✅ Broad exception handling replaced (30+ sites)
- ✅ Context managers for Camera and Recorder
- ✅ Settings injection 100% complete
- ✅ CI YAML syntax fixed

Refs: #phase-1"

git push origin main
```

---

## 🏗️ FASE 2: EXTRAÇÃO DE GOD OBJECTS (Semanas 3-4)

**Branch Base**: `refactor/phase-2-god-objects` (criar APÓS Phase 1 mergeada em main)

### ⚡ Grupo Paralelo 2A (Independentes)

Estes 2 agentes podem trabalhar **simultaneamente**:

#### Agent-6: HardwareCoordinator Extraction

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P2-T1"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install

# Criar branch de fase a partir da main ATUALIZADA (com Phase 1)
git checkout main
git pull origin main
git checkout -b refactor/phase-2-god-objects

# Ler instruções
grep -A 500 "TAREFA P2-T1: Extract HardwareCoordinator" PLANO_REFATORACAO_PARALELA_PARTE2.md

# Criar branch de tarefa
git checkout -b task/p2-t1-hardware-coordinator

# Verificar tamanho atual do MainViewModel
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar 5383 linhas

# Implementar conforme Passos 1-4
# - Criar HardwareCoordinator (~400 linhas)
# - Criar testes (~300 linhas)
# - Remover ~800 linhas de MainViewModel
# - Atualizar __main__.py

# Verificar redução
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar ~4500 linhas (redução de ~800)

# Testar
poetry run pytest tests/core/test_hardware_coordinator.py -v
poetry run pytest -q

# Commit e PR
git add src/zebtrack/core/hardware_coordinator.py \
        tests/core/test_hardware_coordinator.py \
        src/zebtrack/core/main_view_model.py \
        src/zebtrack/__main__.py

git commit -m "refactor(p2-t1): Extract HardwareCoordinator from MainViewModel

- Created HardwareCoordinator class (~400 lines)
- Manages camera and Arduino hardware lifecycle
- Removed ~800 lines from MainViewModel
- Updated dependency injection in __main__.py
- Added 20+ tests for HardwareCoordinator

MainViewModel: 5383 → ~4500 lines (-883)

Refs: #phase-2"

git push origin task/p2-t1-hardware-coordinator

gh pr create \
  --base refactor/phase-2-god-objects \
  --head task/p2-t1-hardware-coordinator \
  --title "Phase 2 Task 1: Extract HardwareCoordinator" \
  --body "..."
```

**⏰ Tempo Estimado**: 4 dias

---

#### Agent-7: AnalysisCoordinator Extraction

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P2-T2"

**Comandos de Início**:

```bash
# Setup (igual ao Agent-6)
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-2-god-objects

# Ler instruções
grep -A 600 "TAREFA P2-T2: Extract AnalysisCoordinator" PLANO_REFATORACAO_PARALELA_PARTE2.md

# Criar branch de tarefa
git checkout -b task/p2-t2-analysis-coordinator

# Implementar conforme Passos 1-3
# - Criar AnalysisCoordinator (~500 linhas)
# - Criar testes (~350 linhas)
# - Remover ~900 linhas de MainViewModel

# Verificar redução
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar ~4400 linhas (redução de ~900)

# Testar
poetry run pytest tests/core/test_analysis_coordinator.py -v
poetry run pytest -q

# Commit e PR
git commit -m "refactor(p2-t2): Extract AnalysisCoordinator from MainViewModel

- Created AnalysisCoordinator class (~500 lines)
- Manages batch video analysis workflows
- Removed ~900 lines from MainViewModel
- Added 15+ tests for AnalysisCoordinator

MainViewModel: 5383 → ~4400 lines (-983)

Refs: #phase-2"

git push origin task/p2-t2-analysis-coordinator
gh pr create --base refactor/phase-2-god-objects --head task/p2-t2-analysis-coordinator --title "..." --body "..."
```

**⏰ Tempo Estimado**: 4 dias

---

### ⚡ Grupo Paralelo 2B (Após 2A mergeado)

#### Agent-8: MainViewModel Final Refactor

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P2-T3"

**Pré-requisito**: P2-T1 E P2-T2 devem estar mergeados em `refactor/phase-2-god-objects`

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install

# Atualizar com P2-T1 e P2-T2 mergeados
git checkout refactor/phase-2-god-objects
git pull origin refactor/phase-2-god-objects

# Criar branch
git checkout -b task/p2-t3-mainviewmodel-refactor

# Verificar linha count atual (deve ter ambas reduções anteriores)
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar ~3500-3600 linhas

# Implementar integrações finais
# - Delegar métodos para HardwareCoordinator
# - Delegar métodos para AnalysisCoordinator
# - Reduzir 11 → 7 dependências no construtor
# - Objetivo final: <2000 linhas

# Meta final
wc -l src/zebtrack/core/main_view_model.py
# Deve mostrar <2000 linhas

# Testar
poetry run pytest -q
poetry run pytest -m gui -n0

# Commit e PR
git commit -m "refactor(p2-t3): Final MainViewModel refactoring

- Integrated HardwareCoordinator and AnalysisCoordinator
- Reduced constructor dependencies: 11 → 7
- Delegated all hardware/analysis logic to coordinators
- Final size: <2000 lines (from 5383)

Total reduction: 5383 → <2000 lines (-63%)

Refs: #phase-2"

git push origin task/p2-t3-mainviewmodel-refactor
gh pr create --base refactor/phase-2-god-objects --head task/p2-t3-mainviewmodel-refactor --title "..." --body "..."
```

**⏰ Tempo Estimado**: 3 dias

---

### 📋 Ordem de Merge - Fase 2

```text
1. ✅ P2-T1 (HardwareCoordinator)    → Merge em paralelo com P2-T2
2. ✅ P2-T2 (AnalysisCoordinator)    → Merge em paralelo com P2-T1
3. ✅ P2-T3 (MainViewModel Refactor) → Merge APÓS P2-T1 E P2-T2
4. ✅ Merge refactor/phase-2-god-objects → main
```

---

## 🧪 FASE 3: TESTES E QUALIDADE (Semanas 5-6)

**Branch Base**: `refactor/phase-3-testing-quality` (criar APÓS Phase 2 mergeada)

### ⚡ Grupo Paralelo 3A (Todos independentes)

Estes 4 agentes podem trabalhar **simultaneamente**:

#### Agent-9: Test Isolation Fixes

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P3-T1"

**Comandos de Início**:

```bash
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-3-testing-quality
git checkout -b task/p3-t1-test-isolation

# Ler instruções
grep -A 100 "TAREFA P3-T1: Fix Test Isolation" PLANO_REFATORACAO_PARALELA_PARTE2.md

# Identificar testes problemáticos
poetry run pytest -q 2>&1 | grep -i "ttkbootstrap"

# Implementar fix (marcar ou isolar 11 testes de UI)
# Adicionar @pytest.mark.skipif ou fixtures de isolamento

# Validar
poetry run pytest -q
# Todos devem passar

# Commit e PR
git commit -m "test(p3-t1): Fix test isolation issues

- Isolated 11 UI component tests
- Added proper skipif markers for full suite
- Updated docs/TESTING.md

Refs: #phase-3"
```

**⏰ Tempo Estimado**: 2 dias

---

#### Agent-10: Increase Test Coverage

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P3-T2"

**Comandos de Início**:

```bash
# Setup igual aos outros
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-3-testing-quality
git checkout -b task/p3-t2-coverage-increase

# Ver cobertura atual
poetry run pytest --cov=zebtrack --cov-report=term-missing
# Deve mostrar ~70%

# Identificar gaps
poetry run pytest --cov=zebtrack --cov-report=html
# Abrir htmlcov/index.html

# Adicionar testes para atingir 80%
# Focar em: edge cases, error paths, branches não cobertas

# Validar meta
poetry run pytest --cov=zebtrack --cov-report=term
# Deve mostrar ≥80%

# Commit e PR
git commit -m "test(p3-t2): Increase test coverage to 80%

- Added edge case tests
- Added error path tests  
- Increased coverage: 70% → 80%+
- Updated pyproject.toml: --cov-fail-under=80

Refs: #phase-3"
```

**⏰ Tempo Estimado**: 4 dias

---

#### Agent-11: Integration Tests

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P3-T3"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-3-testing-quality
git checkout -b task/p3-t3-integration-tests

# Criar diretório para integration tests
mkdir -p tests/integration

# Implementar 10+ testes end-to-end
# - Wizard workflows completos
# - Video processing pipelines
# - Project lifecycle

# Executar
poetry run pytest tests/integration/ -v

# Validar no CI
poetry run pytest -q

# Commit e PR
git commit -m "test(p3-t3): Add integration tests

- Added 10+ end-to-end tests
- Wizard workflow integration tests
- Video processing pipeline tests
- All pass in CI

Refs: #phase-3"
```

**⏰ Tempo Estimado**: 3 dias

---

#### Agent-12: Code Quality Improvements

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P3-T4"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-3-testing-quality
git checkout -b task/p3-t4-code-quality

# Identificar valores hardcoded
grep -r "640\|480\|30\|0.5" src/ --include="*.py" | grep -v "test"

# Extrair para constantes
# - Color maps como class constants
# - Magic numbers para configuração
# - Structured logging consistente

# Validar
poetry run ruff check .
poetry run pytest -q

# Commit e PR
git commit -m "refactor(p3-t4): Code quality improvements

- Extracted 15+ hardcoded values to constants
- Standardized structured logging
- Color maps as class constants
- Optimized tree clearing

Refs: #phase-3"
```

**⏰ Tempo Estimado**: 3 dias

---

### 📋 Ordem de Merge - Fase 3

```text
1. ✅ P3-T1, P3-T2, P3-T3, P3-T4 → Merge em qualquer ordem (paralelo total)
2. ✅ Merge refactor/phase-3-testing-quality → main
```

---

## 🚀 FASE 4: PERFORMANCE E DOCUMENTAÇÃO (Semana 7)

**Branch Base**: `refactor/phase-4-performance-docs` (criar APÓS Phase 3 mergeada)

### ⚡ Grupo Paralelo 4A (Independentes)

Estes 3 agentes podem trabalhar **simultaneamente**:

#### Agent-13: Performance Optimization

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P4-T1"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-4-performance-docs
git checkout -b task/p4-t1-performance-optimization

# Profiling
poetry run python -m cProfile -o profile.stats -m zebtrack

# Analisar hot paths
poetry run python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"

# Implementar otimizações
# - Color maps cacheados
# - Tree clearing batch operations
# - etc

# Benchmark antes/depois
# Documentar melhorias

# Commit e PR
git commit -m "perf(p4-t1): Performance optimizations

- Profiled hot paths
- Optimized color map operations
- Optimized tree clearing  
- Documented benchmarks

Refs: #phase-4"
```

**⏰ Tempo Estimado**: 2 dias

---

#### Agent-14: DevOps Tooling

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P4-T2"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
poetry install
git checkout main
git pull origin main
git checkout -b refactor/phase-4-performance-docs
git checkout -b task/p4-t2-devops-tooling

# Criar .pre-commit-config.yaml
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest-fast
        entry: poetry run pytest -q
        language: system
        pass_filenames: false
EOF

# Testar hooks
poetry run pre-commit install
poetry run pre-commit run --all-files

# Atualizar CONTRIBUTING.md
# Adicionar instruções de setup de hooks

# Commit e PR
git commit -m "build(p4-t2): Add DevOps tooling

- Configured pre-commit hooks (ruff, pytest)
- Updated CONTRIBUTING.md with setup instructions
- Ensures quality checks before commit

Refs: #phase-4"
```

**⏰ Tempo Estimado**: 1 dia

---

#### Agent-15: Documentation Curation (CRÍTICO)

**Arquivo de Referência**: `PLANO_REFATORACAO_PARALELA_PARTE2.md` → Seção "TAREFA P4-T3"

**Comandos de Início**:

```bash
# Setup
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout main
git pull origin main
git checkout -b refactor/phase-4-performance-docs
git checkout -b task/p4-t3-documentation-curation

# Ler instruções COMPLETAS (tarefa mais complexa)
grep -A 800 "TAREFA P4-T3: Documentation Curation" PLANO_REFATORACAO_PARALELA_PARTE2.md

# Passo 1: Auditoria
find . -name "*.md" | grep -v node_modules | grep -v venv > all_docs.txt
cat all_docs.txt
# Categorizar cada arquivo: MANTER, CONSOLIDAR, ARQUIVAR, DELETAR

# Passo 2: Criar estrutura alvo
mkdir -p docs/archive/refactoring_history
mkdir -p docs/archive/test_reports
mkdir -p docs/archive/planning
mkdir -p docs/MIGRATION_GUIDES

# Passo 3: Consolidar documentos
# Ver instruções detalhadas nos Passos 3-7 do plano

# Passo 4: Criar docs/README.md (índice principal)
# Passo 5: Atualizar README.md raiz
# Passo 6: Mover obsoletos para archive/
# Passo 7: Validar links

# Validar Markdown
markdownlint-cli2 "docs/**/*.md"

# Validar TODOs eliminados
grep -r "TODO\|FIXME" docs/ --include="*.md"
# Deve retornar zero (ou apenas em archive/)

# Commit e PR
git commit -m "docs(p4-t3): Comprehensive documentation curation

- Audited all repository documentation
- Consolidated redundant documents
- Archived obsolete content to docs/archive/
- Created unified docs/README.md index
- Updated root README.md
- Validated all internal links
- Zero linting errors
- Zero TODOs in main docs

Documentation structure:
- docs/README.md (main index)
- docs/ARCHITECTURE.md (updated)
- docs/USER_GUIDE.md (consolidated)
- docs/DEVELOPER_GUIDE.md (consolidated)
- docs/TESTING_GUIDE.md (consolidated)
- docs/archive/ (historical content)

Refs: #phase-4"
```

**⏰ Tempo Estimado**: 3 dias

---

### 📋 Ordem de Merge - Fase 4

```text
1. ✅ P4-T1, P4-T2 → Merge em qualquer ordem (paralelo)
2. ✅ P4-T3 (Documentation) → Merge POR ÚLTIMO (documenta todas as mudanças)
3. ✅ Merge refactor/phase-4-performance-docs → main
```

---

## 📊 RESUMO DE PARALELIZAÇÃO

### Matriz de Dependências

| Fase | Tarefa | Agente | Pode Iniciar Quando | Trabalho Paralelo Com |
|------|--------|--------|---------------------|------------------------|
| 1 | P1-T5 | Agent-5 | Imediatamente | NENHUM (bloqueante) |
| 1 | P1-T1 | Agent-1 | P1-T5 mergeado | P1-T2 |
| 1 | P1-T2 | Agent-2 | P1-T5 mergeado | P1-T1 |
| 1 | P1-T3 | Agent-3 | Imediatamente | P1-T4 |
| 1 | P1-T4 | Agent-4 | Imediatamente | P1-T3 |
| 2 | P2-T1 | Agent-6 | Fase 1 completa | P2-T2 |
| 2 | P2-T2 | Agent-7 | Fase 1 completa | P2-T1 |
| 2 | P2-T3 | Agent-8 | P2-T1 E P2-T2 mergeados | NENHUM |
| 3 | P3-T1 | Agent-9 | Fase 2 completa | P3-T2, P3-T3, P3-T4 |
| 3 | P3-T2 | Agent-10 | Fase 2 completa | P3-T1, P3-T3, P3-T4 |
| 3 | P3-T3 | Agent-11 | Fase 2 completa | P3-T1, P3-T2, P3-T4 |
| 3 | P3-T4 | Agent-12 | Fase 2 completa | P3-T1, P3-T2, P3-T3 |
| 4 | P4-T1 | Agent-13 | Fase 3 completa | P4-T2 |
| 4 | P4-T2 | Agent-14 | Fase 3 completa | P4-T1 |
| 4 | P4-T3 | Agent-15 | Fase 3 completa | P4-T1, P4-T2 |

### Grupos de Trabalho Paralelo

**Máximo de Agentes Trabalhando Simultaneamente**: 4 agentes (na Fase 3)

**Fase 1**:

- **Onda 1**: 1 agente (Agent-5) - 2 dias
- **Onda 2**: 4 agentes (Agent-1, Agent-2, Agent-3, Agent-4) - 3 dias
- **Total**: ~5 dias com paralelização

**Fase 2**:

- **Onda 1**: 2 agentes (Agent-6, Agent-7) - 4 dias
- **Onda 2**: 1 agente (Agent-8) - 3 dias
- **Total**: ~7 dias com paralelização

**Fase 3**:

- **Onda 1**: 4 agentes (Agent-9, Agent-10, Agent-11, Agent-12) - 4 dias
- **Total**: ~4 dias com paralelização

**Fase 4**:

- **Onda 1**: 3 agentes (Agent-13, Agent-14, Agent-15) - 3 dias
- **Total**: ~3 dias com paralelização

**Total do Projeto**: ~19 dias úteis (~4 semanas) com paralelização máxima

---

## ✅ CHECKLIST DO COORDENADOR

### Por Fase

- [ ] **Fase 1 Iniciada**: Branch `refactor/phase-1-critical-fixes` criada
- [ ] **P1-T5 Mergeado**: Custom exceptions disponíveis para P1-T1 e P1-T2
- [ ] **Fase 1 Completa**: 5 PRs mergeados, branch mergeada em main
- [ ] **Fase 2 Iniciada**: Branch `refactor/phase-2-god-objects` criada a partir da main atualizada
- [ ] **P2-T1 e P2-T2 Mergeados**: Coordinators disponíveis para P2-T3
- [ ] **Fase 2 Completa**: 3 PRs mergeados, MainViewModel <2000 linhas, branch mergeada em main
- [ ] **Fase 3 Iniciada**: Branch `refactor/phase-3-testing-quality` criada
- [ ] **Fase 3 Completa**: 4 PRs mergeados, coverage 80%+, branch mergeada em main
- [ ] **Fase 4 Iniciada**: Branch `refactor/phase-4-performance-docs` criada
- [ ] **P4-T3 Mergeado Por Último**: Documentação atualizada com todas as mudanças
- [ ] **Projeto Completo**: Todas as fases mergeadas, CI passing, métricas atingidas

---

## 🆘 SUPORTE E TROUBLESHOOTING

### Para Agentes

**Problema**: "Não consigo encontrar minha tarefa no plano"

**Solução**:

```bash
# Buscar por ID da tarefa
grep -n "TAREFA P[0-9]-T[0-9]" PLANO_REFATORACAO_PARALELA_*.md

# Buscar por nome
grep -n "Hardware" PLANO_REFATORACAO_PARALELA_*.md
```

**Problema**: "Meus testes estão falhando após merge"

**Solução**:

```bash
# Atualizar branch com latest
git fetch origin
git merge origin/refactor/phase-X-name

# Reinstalar dependências
poetry install --sync

# Limpar cache
poetry run pytest --cache-clear
poetry run pytest -q
```

**Problema**: "Conflitos de merge"

**Solução**:

```bash
# Ver arquivos em conflito
git status

# Para cada arquivo, editar e resolver
# Remover markers: <<<<<<< ======= >>>>>>>

# Após resolver
git add <arquivo>
git commit
```

### Para Coordenador

**Responsabilidades**:

1. Criar branches de fase no momento correto
2. Revisar e aprovar PRs
3. Garantir ordem de merge correta
4. Resolver conflitos entre tarefas
5. Fazer merge de branches de fase em main
6. Monitorar CI/CD
7. Comunicar bloqueios aos agentes

**Comandos Úteis**:

```bash
# Ver status de todas as branches
git branch -a

# Ver PRs abertos (requer GitHub CLI)
gh pr list --base refactor/phase-X-name

# Ver diff entre branches
git diff refactor/phase-1-critical-fixes...main

# Cherry-pick commit específico se necessário
git cherry-pick <commit-hash>
```

---

## 📞 CONTATOS E RECURSOS

- **Repositório**: <https://github.com/MarkSant/ZebTrack-AI>
- **Issues**: <https://github.com/MarkSant/ZebTrack-AI/issues>
- **Discussions**: <https://github.com/MarkSant/ZebTrack-AI/discussions>

**Documentação de Referência**:

- `docs/ARCHITECTURE.md` - Arquitetura do sistema
- `docs/DEVELOPER_GUIDE.md` - Guia do desenvolvedor
- `docs/TESTING_GUIDE.md` - Guia de testes
- `CONTRIBUTING.md` - Como contribuir

---

**Última Atualização**: 9 de Novembro de 2025

**Versão**: 1.0

**Status**: Pronto para Execução
