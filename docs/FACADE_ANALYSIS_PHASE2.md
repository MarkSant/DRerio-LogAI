# Análise de Facades - Fase 2 Refatoração MainViewModel

**Data**: 2025-01-19
**Objetivo**: Remover 86 métodos facade do MainViewModel
**Impacto Estimado**: -340 linhas de código

## Resumo Executivo

Total de facades identificados: **86 métodos**

### Distribuição por Orchestrator

| Orchestrator | Qtd Facades | % Total |
|--------------|-------------|---------|
| UIStateController | 23 | 26.7% |
| ProjectOrchestrator | 17 | 19.8% |
| RecordingSessionOrchestrator | 15 | 17.4% |
| VideoProcessingOrchestrator | 7 | 8.1% |
| ProcessingConfigOrchestrator | 7 | 8.1% |
| ModelDiagnosticsOrchestrator | 7 | 8.1% |
| ZoneArenaOrchestrator | 3 | 3.5% |
| CalibrationOrchestrator | 3 | 3.5% |
| AnalysisOrchestrator | 3 | 3.5% |
| LiveCameraCoordinator | 1 | 1.2% |
| **TOTAL** | **86** | **100%** |

## Estratégia de Remoção

### Fase 2.1: Criar OrchestratorRegistry 🎯

Criar um registry centralizado para acesso aos orchestrators:

```python
class OrchestratorRegistry:
    """Registry centralizado para acessar todos os orchestrators."""

    def __init__(self, main_view_model):
        self.recording = main_view_model.recording_session_orchestrator
        self.project = main_view_model.project_orchestrator
        self.ui_state = main_view_model.ui_state_controller
        self.video_processing = main_view_model.video_processing_orchestrator
        self.analysis = main_view_model.analysis_orchestrator
        self.processing_config = main_view_model.processing_config_orchestrator
        self.model_diagnostics = main_view_model.model_diagnostics_orchestrator
        self.zone_arena = main_view_model.zone_arena_orchestrator
        self.calibration = main_view_model.calibration_orchestrator
        self.live_camera = main_view_model.live_camera_coordinator
```

### Fase 2.2: Padrão de Substituição

**ANTES (Facade):**
```python
# MainViewModel
def close_project(self) -> None:
    """Facade - delegates to ProjectOrchestrator."""
    return self.project_orchestrator.close_project()

# Caller (GUI ou event handler)
self.controller.close_project()
```

**DEPOIS (Direto):**
```python
# MainViewModel - método removido!

# Caller (GUI ou event handler)
self.controller.project_orchestrator.close_project()
# ou via registry:
self.controller.orchestrators.project.close_project()
```

### Fase 2.3: Atualização de Callers

**Locais a atualizar:**
1. `src/zebtrack/ui/gui.py` - Chamadas diretas da GUI
2. Event handlers em `MainViewModel.bind_events()`
3. Testes em `tests/`

### Fase 2.4: Ordem de Remoção Recomendada

Remover facades em ordem crescente de complexidade:

1. **UIStateController** (23 facades) - BAIXA COMPLEXIDADE
   - Métodos simples de UI
   - Pouco acoplamento
   - Fácil de testar

2. **RecordingSessionOrchestrator** (15 facades) - MÉDIA COMPLEXIDADE
   - Estado de recording
   - Callbacks de UI
   - Moderadamente acoplado

3. **ProjectOrchestrator** (17 facades) - MÉDIA/ALTA COMPLEXIDADE
   - Workflows de projeto
   - Muitos callers na GUI
   - Alto acoplamento

4. **Outros Orchestrators** (31 facades) - VARIÁVEL
   - Processar caso a caso
   - Validar impacto em testes

## Riscos e Mitigações

### Riscos

1. **🔴 ALTO**: Quebra de testes existentes
   - **Mitigação**: Executar testes após cada batch de remoções

2. **🟡 MÉDIO**: Chamadas indiretas via reflection/eval
   - **Mitigação**: Buscar por `getattr`, `eval`, `exec` no código

3. **🟢 BAIXO**: Event handlers quebrados
   - **Mitigação**: Buscar todos os usos de cada método antes de remover

### Checklist de Segurança

Antes de remover cada facade:
- [ ] Identificar TODOS os callers (grep no codebase)
- [ ] Atualizar cada caller para chamar orchestrator diretamente
- [ ] Executar testes relacionados
- [ ] Validar que nenhum teste quebrou
- [ ] Commit incremental

## Métricas de Sucesso

**Antes:**
- MainViewModel: 2.797 linhas, 155 métodos
- 86 métodos facade (~340 linhas)

**Meta Após Fase 2:**
- MainViewModel: ~2.457 linhas, ~69 métodos
- 0 métodos facade
- Cobertura de testes: mantida em 70%+
- Todos os testes passando

## Próximos Passos

1. ✅ Análise completa (este documento)
2. ⏳ Criar OrchestratorRegistry
3. ⏳ Remover batch 1: UIStateController (23 facades)
4. ⏳ Remover batch 2: RecordingSessionOrchestrator (15 facades)
5. ⏳ Remover batch 3: ProjectOrchestrator (17 facades)
6. ⏳ Remover batch 4: Outros (31 facades)
7. ⏳ Validação final (todos os testes)

---

**Estimativa de Tempo**: 3-4 dias
**Risco Geral**: 🟡 MÉDIO
**Compatibilidade Reversa**: ⚠️ BREAKING - Mudanças de API
