# Agent Instructions - Phase 3 (PARALELO)

**✅ Todos os agentes deste grupo podem trabalhar SIMULTANEAMENTE**

## 📋 Visão Geral
- **Grupo de Execução**: Phase 3 (Testing & Quality)
- **Número de Agentes**: 3 (paralelo total)
- **Dependências**: Phase 2 merged
- **Branch**: `refactor/phase-3-testing-quality`
- **Duração**: 2 semanas (Week 5-6)

## ⚠️ PRÉ-REQUISITO

```bash
# Verifique que Phase 2 foi merged
git checkout main
git pull origin main

# Crie branch Phase 3
git checkout -b refactor/phase-3-testing-quality
git push -u origin refactor/phase-3-testing-quality
```

---

## 🤖 AGENT-9: Increase Test Coverage (P3-T1)

### 📌 Contexto
Você é o **Agent-9** responsável por aumentar cobertura de testes de 70% para 80%+.

### 🎯 Objetivo
Adicionar testes para módulos com baixa cobertura: `analysis/`, `io/`, `plugins/`.

### 📂 Acesso
```bash
git clone https://github.com/MarkSant/ZebTrack-AI.git
cd ZebTrack-AI
git checkout refactor/phase-3-testing-quality
poetry install
poetry shell
```

### 📖 Documentação
**PLANO_REFATORACAO_PARALELA_PARTE2.md** - Seção P3-T1

### 🛠️ Implementação Resumida

#### Passo 1: Identificar Gaps
```bash
# Gere relatório de coverage
poetry run pytest --cov=zebtrack --cov-report=html --cov-report=term-missing

# Abra htmlcov/index.html e identifique módulos < 70%
```

#### Passo 2: Adicionar Testes para analysis/
Crie `tests/test_analysis_service.py`:

```python
"""Comprehensive tests for AnalysisService."""

import pytest
from zebtrack.analysis.analysis_service import AnalysisService


class TestAnalysisService:
    def test_compute_roi_metrics(self, analysis_service, sample_tracks):
        """Compute ROI metrics from tracking data."""
        metrics = analysis_service.compute_roi_metrics(sample_tracks)
        assert "time_in_roi" in metrics
        assert metrics["time_in_roi"] >= 0

    def test_generate_heatmap(self, analysis_service, sample_tracks):
        """Generate heatmap from tracking data."""
        heatmap = analysis_service.generate_heatmap(sample_tracks)
        assert heatmap is not None
        assert heatmap.shape[0] > 0
```

#### Passo 3: Adicionar Testes para io/
#### Passo 4: Adicionar Testes para plugins/
#### Passo 5: Validar Coverage

```bash
# Verifique que coverage >= 80%
poetry run pytest --cov=zebtrack --cov-report=term-missing | grep "TOTAL"
```

#### Passo 6: Commit
```bash
git add tests/
git commit -m "test: Increase coverage from 70% to 80%+ (P3-T1)

- Add comprehensive tests for analysis service
- Add tests for io module (video_source, recorder)
- Add tests for plugins (YOLO, ByteTrack)
- Achieve 80%+ total coverage

Phase: 3
Task: P3-T1
Agent: Agent-9"

git push origin refactor/phase-3-testing-quality
```

### ✅ Critérios
- [ ] Coverage >= 80%
- [ ] Mínimo 50 novos testes
- [ ] Todos os testes passando

### ⏱️ Estimativa: ~6-8 horas

---

## 🤖 AGENT-10: Fix Deprecation Warnings (P3-T2)

### 📌 Contexto
Você é o **Agent-10** responsável por corrigir 15+ warnings de deprecação (Python 3.12, Pydantic v2).

### 🎯 Objetivo
Eliminar todos os deprecation warnings visíveis em testes.

### 📖 Documentação
**docs/TESTING_DEPRECATION_WARNINGS.md**

### 🛠️ Implementação Resumida

#### Passo 1: Identificar Warnings
```bash
# Execute testes com warnings
poetry run pytest -v -W default 2>&1 | grep -i "deprecat"
```

#### Passo 2: Corrigir Pydantic Warnings
```python
# ANTES (Pydantic v1 style)
class Settings(BaseModel):
    class Config:
        extra = "forbid"

# DEPOIS (Pydantic v2 style)
class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

#### Passo 3: Corrigir datetime.utcnow()
```python
# ANTES
from datetime import datetime
now = datetime.utcnow()

# DEPOIS
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
```

#### Passo 4: Commit
```bash
git add src/
git commit -m "fix: Resolve all deprecation warnings (P3-T2)

- Migrate Pydantic v1 to v2 syntax (ConfigDict)
- Replace datetime.utcnow() with timezone-aware datetime.now()
- Fix pkg_resources deprecations
- Achieve zero deprecation warnings in test suite

Phase: 3
Task: P3-T2
Agent: Agent-10"

git push origin refactor/phase-3-testing-quality
```

### ✅ Critérios
- [ ] Zero deprecation warnings
- [ ] Código compatível com Python 3.12+
- [ ] Pydantic v2 compliant

### ⏱️ Estimativa: ~3-4 horas

---

## 🤖 AGENT-11: Improve Docstrings (P3-T3)

### 📌 Contexto
Você é o **Agent-11** responsável por melhorar docstrings em módulos principais.

### 🎯 Objetivo
Garantir 100% de docstrings em módulos públicos (`core/`, `ui/`, `analysis/`).

### 🛠️ Implementação Resumida

#### Passo 1: Verificar Gaps
```bash
# Use pydocstyle para encontrar docstrings faltando
poetry add --group dev pydocstyle
poetry run pydocstyle src/zebtrack/core/
```

#### Passo 2: Adicionar Docstrings
```python
def process_frame(self, frame: np.ndarray) -> list[Detection]:
    """
    Process single frame through detection pipeline.

    Args:
        frame: Input frame as numpy array (H, W, C) in BGR format

    Returns:
        List of Detection objects with bounding boxes and confidence scores

    Raises:
        DetectionError: If detection fails

    Example:
        >>> detections = detector.process_frame(frame)
        >>> for det in detections:
        ...     print(f"Box: {det.bbox}, Confidence: {det.confidence}")
    """
```

#### Passo 3: Commit
```bash
git add src/
git commit -m "docs: Add comprehensive docstrings to core modules (P3-T3)

- Add Google-style docstrings to all public functions/classes
- Include Args, Returns, Raises, Examples sections
- Achieve 100% docstring coverage in core/, ui/, analysis/

Phase: 3
Task: P3-T3
Agent: Agent-11"

git push origin refactor/phase-3-testing-quality
```

### ✅ Critérios
- [ ] 100% docstrings em módulos públicos
- [ ] Google-style format
- [ ] Zero pydocstyle errors

### ⏱️ Estimativa: ~4-5 horas

---

## 📊 Resumo Phase 3

### Execução Paralela Total
✅ Todos os 3 agentes podem trabalhar simultaneamente:
- Agent-9: Testes
- Agent-10: Deprecations
- Agent-11: Docstrings

### Comunicação de Conclusão
```
✅ PHASE 3 CONCLUÍDA

Melhorias:
- Coverage: 70% → 82% (+50 testes)
- Warnings: 15+ → 0
- Docstrings: 60% → 100%

Branch: refactor/phase-3-testing-quality
Próximo: Merge para main e iniciar Phase 4
```

---

**Início**: ___________
**Conclusão**: ___________
**Status**: [ ] Não Iniciado | [ ] Em Progresso | [ ] Concluído
