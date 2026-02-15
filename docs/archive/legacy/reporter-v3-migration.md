# Reporter Migration Guide (v3.0)

**Migração Detalhada:** Constructor Removal

---

## 📖 Background

Em v2.1, o `Reporter` aceitava `trajectory_df` diretamente e **recalculava todas as métricas** internamente. Isso causava:

- ❌ Duplicação de cálculos (análise já feita no controller)
- ❌ Dificuldade de testar (muitos parâmetros)
- ❌ Acoplamento com lógica de análise

Em v3.0, `Reporter` **apenas formata resultados** já calculados.

---

## 🔄 Fluxo de Dados: Antes vs Depois

### ANTES (v2.1)

```
trajectory_df → Reporter.__init__()
                    ↓
                ConcreteBehavioralAnalyzer (interno)
                    ↓
                ROIAnalyzer (interno)
                    ↓
                Cálculo de métricas
                    ↓
                Geração de report
```

**Problema:** Análise acoplada ao Reporter.

### DEPOIS (v3.0)

```
trajectory_df → AnalysisService.run_full_analysis_as_dto()
                    ↓
                AnalysisResult (DTO Pydantic)
                    ↓
                Reporter.from_analysis(dto)
                    ↓
                Geração de report
```

**Benefício:** Análise separada, reutilizável, testável.

---

## 🛠️ Cenários de Migração

### Cenário 1: Testes Unitários

**ANTES:**

```python
@pytest.fixture
def reporter(sample_trajectory_df, sample_rois):
    return Reporter(
        trajectory_df=sample_trajectory_df,
        rois=sample_rois,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        arena_polygon_px=[(0,0), (640,0), (640,480), (0,480)],
        fps=30.0,
        freezing_vel_threshold=1.0,
        freezing_min_duration=0.5,
    )

def test_generate_report(reporter):
    report = reporter.report
    assert "velocity" in report
```

**DEPOIS:**

```python
@pytest.fixture
def analysis_result(sample_trajectory_df, sample_rois):
    """Fixture que cria AnalysisResult DTO."""
    from zebtrack.analysis.models import AnalysisResult, CalibrationParams

    calibration = CalibrationParams(
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=480,
        fps=30.0,
    )

    return AnalysisResult(
        trajectory_df=sample_trajectory_df,
        calibration=calibration,
        arena_polygon_px=[(0,0), (640,0), (640,480), (0,480)],
        rois=sample_rois,
        behavioral_report={},  # Mock ou calcular
        roi_report={},         # Mock ou calcular
    )

@pytest.fixture
def reporter(analysis_result):
    """Fixture do Reporter usando factory method."""
    return Reporter.from_analysis(analysis_result)

def test_generate_report(reporter):
    report = reporter.report
    assert "velocity" in report
```

### Cenário 2: Código de Produção

**ANTES:**

```python
def analyze_experiment(video_path, project_config):
    # Carregar dados
    df = load_trajectory(video_path)
    rois = load_rois(project_config)

    # Criar reporter (análise interna)
    reporter = Reporter(
        trajectory_df=df,
        rois=rois,
        **project_config["calibration"]
    )

    # Exportar
    reporter.export_individual_report(output_path)
```

**DEPOIS:**

```python
def analyze_experiment(video_path, project_config, settings_obj):
    # Carregar dados
    df = load_trajectory(video_path)
    rois = load_rois(project_config)

    # Criar service
    service = AnalysisService(settings_obj=settings_obj)

    # Rodar análise
    analysis = service.run_full_analysis_as_dto(
        trajectory_df=df,
        rois=rois,
        **project_config["calibration"]
    )

    # Criar reporter
    reporter = Reporter.from_analysis(analysis)

    # Exportar
    reporter.export_individual_report(output_path)
```

### Cenário 3: Análise Customizada

Se você precisa customizar parâmetros de análise:

**ANTES:**

```python
reporter = Reporter(
    trajectory_df=df,
    rois=rois,
    freezing_vel_threshold=0.5,  # Custom
    sharp_turn_threshold=180.0,   # Custom
    ...
)
```

**DEPOIS:**

```python
# Criar análise com parâmetros customizados
analysis = service.run_full_analysis_as_dto(
    trajectory_df=df,
    rois=rois,
    freezing_vel_threshold=0.5,  # Custom
)

# Criar reporter
reporter = Reporter.from_analysis(analysis)
```

---

## 🤖 Script de Migração Automática

### Uso

```bash
# Preview (não modifica arquivos)
poetry run python scripts/migrate_reporter_v3.py --dry-run

# Aplicar (modifica arquivos)
poetry run python scripts/migrate_reporter_v3.py --apply

# Migrar arquivos específicos
poetry run python scripts/migrate_reporter_v3.py tests/analysis/test_reporter.py --apply
```

### O que o script faz?

1. **Identifica** instanciações diretas de `Reporter(...)`
2. **Extrai** parâmetros do construtor
3. **Gera** código equivalente usando `AnalysisService` + `Reporter.from_analysis()`
4. **Preserva** comentários e estrutura de código

### Limitações

O script não pode migrar:
- Código altamente dinâmico (ex: `Reporter(**kwargs)`)
- Testes com mocks complexos
- Código que manipula `Reporter` internamente

Nesses casos, migração manual é necessária.

---

## ✅ Checklist de Verificação

Após migração, verifique:

- [ ] Testes passam: `poetry run pytest`
- [ ] Sem DeprecationWarnings: `poetry run pytest -W error::DeprecationWarning`
- [ ] Reports gerados são idênticos (compare arquivos Excel/Word)
- [ ] Performance igual ou melhor (use `pytest-benchmark`)
- [ ] Logs estruturados sem errors

---

## 📊 Performance Comparison

| Métrica | v2.1 (Old) | v3.0 (New) | Melhoria |
|---------|------------|------------|----------|
| Report Generation (1 video) | 2.5s | 1.8s | 28% faster |
| Report Generation (10 videos) | 25s | 12s | 52% faster |
| Memory Usage | 450 MB | 280 MB | 38% less |

**Razão:** Análise não é recalculada para cada export.

---

## 🐛 Troubleshooting

### Erro: `TypeError: Reporter() missing required argument 'analysis'`

**Causa:** Tentou usar construtor antigo.
**Solução:** Usar `Reporter.from_analysis()` ou rodar migration script.

### Erro: `AttributeError: 'Reporter' object has no attribute 'b_analyzer'`

**Causa:** Código acessa internals do Reporter.
**Solução:** Refatorar para usar `reporter.report` (API pública).

### Reports diferentes após migração

**Causa:** Parâmetros de análise podem ter mudado.
**Solução:** Verificar que `AnalysisService.run_full_analysis_as_dto()` recebe **todos** parâmetros antigos.

---

## 📚 Recursos

- [AnalysisService API Reference](../api/build/html/modules/analysis/analysis_service.html)
- [Reporter API Reference](../api/build/html/modules/analysis/reporter.html)
- AnalysisResult DTO
