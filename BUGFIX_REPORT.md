# Bug Report - Dead Code Removal

## Data: 31 de Outubro de 2025

## 🐛 Bug Encontrado

### Localização
**Arquivo**: `src/zebtrack/analysis/analysis_service.py`  
**Linhas**: 245-310 (removidas)  
**Método**: `generate_reports()`

### Descrição do Problema

O método `AnalysisService.generate_reports()` estava completamente **quebrado e não utilizado**:

#### Problema 1: Instanciação Incorreta do Reporter
```python
# ❌ CÓDIGO QUEBRADO (linha 270)
reporter = Reporter()  # Reporter requer 12 argumentos obrigatórios!
```

O `Reporter` requer os seguintes argumentos obrigatórios:
- `trajectory_df: pd.DataFrame`
- `metadata: dict`
- `pixelcm_x: float`
- `pixelcm_y: float`
- `video_height_px: int`
- `arena_polygon_px: list[tuple[float, float]]`
- `rois: list[ROI]`
- `fps: float`

#### Problema 2: Chamadas de Métodos Inexistentes
```python
# ❌ CÓDIGO QUEBRADO (linhas 275-284)
summary_path = reporter.export_summary_data(
    report_data=report_data,      # ❌ Parâmetro não existe
    output_dir=output_dir,         # ❌ Parâmetro não existe
    video_name=video_name,         # ❌ Parâmetro não existe
    metadata=metadata,             # ❌ Parâmetro não existe
)
```

A assinatura real de `Reporter.export_summary_data()` é:
```python
def export_summary_data(self, output_path: Path | str, format: str = "excel"):
    # Apenas output_path e format são aceitos
```

#### Problema 3: Código Morto
**Verificação de uso**:
- ✅ Não é chamado em nenhum lugar do código de produção
- ✅ Não é usado em nenhum teste
- ✅ Não faz parte da API pública documentada
- ✅ Foi deixado acidentalmente durante a refatoração DI

### Impacto

**Severidade**: 🟢 **Baixa**  
**Razão**: O método não é usado em nenhum lugar, portanto não afeta funcionalidades existentes.

Se o método fosse chamado, causaria:
- `TypeError: Reporter.__init__() missing 8 required positional arguments`
- Falha imediata na geração de relatórios

### Solução Implementada

**Ação**: Remoção completa do método quebrado (65 linhas)

**Justificativa**:
1. Código não é usado (dead code)
2. Está completamente quebrado
3. A funcionalidade de geração de relatórios já existe corretamente em `MainViewModel._generate_reports_for_video()`
4. Reduz complexidade e manutenção

### Código Correto para Referência

O padrão correto de uso do Reporter está em `MainViewModel.py` linha 4326:

```python
# ✅ USO CORRETO DO REPORTER
reporter = Reporter(
    trajectory_df=trajectory_df,
    metadata=metadata,
    pixelcm_x=pixelcm_x,
    pixelcm_y=pixelcm_y,
    video_height_px=video_height_px,
    arena_polygon_px=arena_polygon_warped,
    rois=rois,
    fps=settings_obj.video_processing.fps,
    roi_colors=roi_colors,
    video_path=path,
    calibration=cal,
    sharp_turn_threshold=settings_obj.video_processing.sharp_turn_threshold_deg_s,
    freezing_threshold=settings_obj.video_processing.freezing_velocity_threshold,
    freezing_duration=settings_obj.video_processing.freezing_min_duration_s,
    smoothing_window_length=settings_obj.trajectory_smoothing.window_length,
    smoothing_polyorder=settings_obj.trajectory_smoothing.polyorder,
)

# Exportar dados
parquet_path = os.path.join(results_dir, f"{experiment_id}_summary.parquet")
reporter.export_summary_data(parquet_path, format="parquet")
```

## ✅ Validação

### Testes Executados
```bash
poetry run pytest tests/ -q --no-cov --tb=no
```

**Resultado**: ✅ **710/711 testes passando (99.86%)**
- 1 skip legítimo (problema de ambiente Tkinter, não relacionado)

### Linting
```bash
poetry run ruff check src/zebtrack/analysis/analysis_service.py
```

**Resultado**: ✅ **Nenhum erro**

## 📊 Estatísticas

| Métrica | Antes | Depois | Melhoria |
|---------|-------|--------|----------|
| Linhas de código | 683 | 618 | -65 linhas (-9.5%) |
| Métodos quebrados | 1 | 0 | 100% |
| Código morto | 65 linhas | 0 | 100% |
| Testes passando | 710/711 | 710/711 | Mantido |

## 🔄 Commits Relacionados

- **95abfd8**: `fix(analysis): Remove broken unused generate_reports method - dead code cleanup`
- **6c04f28**: `refactor(tests): Fix test_logging_config.py and test_single_video_workflow.py for DI - 710/711 passing (99.86%)`

## 📝 Lições Aprendidas

1. **Code Review**: Refatorações grandes podem deixar código morto
2. **Dead Code Detection**: Ferramentas de análise estática poderiam detectar código não usado
3. **Test Coverage**: Código sem testes é candidato a remoção
4. **DI Migration**: Validar que todos os métodos públicos foram atualizados para DI

## ✨ Status Final

✅ **Bug corrigido através de remoção de código morto**  
✅ **Nenhuma funcionalidade afetada**  
✅ **Testes continuam passando**  
✅ **Código mais limpo e mantível**
