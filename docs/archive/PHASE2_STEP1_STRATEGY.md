# Fase 2.1: Estratégia de Refatoração do MainViewModel

## Análise do Problema

O `MainViewModel` (controller.py) tem **5705 linhas** e contém:
- ✅ Responsabilidades corretas (estado UI, delegação)
- ❌ Lógica de negócio que deveria estar em serviços
- ❌ Manipulação direta de arquivos
- ❌ Processamento pesado
- ❌ Conversão de modelos

## Abordagem Pragmática

Dada a complexidade, vamos adotar uma **refatoração incremental**:

### Princípios
1. **Segurança Primeiro**: Manter testes passando
2. **Incremental**: Refatorar método por método
3. **Documentado**: Cada mudança deve ser rastreável
4. **Testável**: Adicionar testes para novas abstrações

---

## Fase 2.1: Refatorações Prioritárias

### Prioridade 1: Criar ModelService (CRÍTICO)

**Problema**: Lógica de gerenciamento de modelos de IA espalhada no controller.

**Métodos a Mover**:
1. `convert_active_weight_to_openvino` → `ModelService.convert_weight`
2. `setup_detector` → `ModelService.setup_detector`  
3. `update_detector_parameters` → `ModelService.update_parameters`
4. Lógica de seleção de peso → `ModelService.select_weight`

**Benefício**: 
- Separa concerns de modelo/IA
- Facilita testes de conversão OpenVINO
- Reduz ~500 linhas do controller

**Status**: 🟡 Planejado

---

### Prioridade 2: Expandir ProjectService (IMPORTANTE)

**Problema**: Operações de I/O de projeto ainda no controller.

**Métodos a Mover**:
1. `save_current_calibration_to_project` → `ProjectService.save_calibration`
2. `save_project_model_overrides` → `ProjectService.save_model_config`
3. `save_manual_arena` → `ProjectService.save_arena_config`
4. `create_project_workflow` → Já foi movido? Verificar

**Benefício**:
- Consolida todo I/O de projeto
- Facilita testes de persistência
- Reduz ~300 linhas do controller

**Status**: 🟡 Planejado

---

### Prioridade 3: Expandir AnalysisService (MÉDIO)

**Problema**: Orquestração de processamento no controller.

**Métodos a Mover**:
1. `process_pending_project_videos` → `AnalysisService.process_videos`
2. Lógica de progresso/callback → `AnalysisService` interno
3. Worker management → `AnalysisService.create_worker`

**Benefício**:
- Separa orquestração de análise
- Facilita paralelização
- Reduz ~400 linhas do controller

**Status**: 🟡 Planejado

---

## Implementação Incremental

### Fase A: Preparação (Esta Sessão)
1. ✅ Criar documento de estratégia (este arquivo)
2. ⏳ Criar ModelService stub
3. ⏳ Identificar dependências exatas
4. ⏳ Escrever testes para comportamento atual

### Fase B: ModelService (Próxima Sessão)
1. Implementar `ModelService.convert_weight()`
2. Refatorar `convert_active_weight_to_openvino()` para delegar
3. Executar testes
4. Repetir para outros métodos

### Fase C: ProjectService (Futuro)
1. Expandir `ProjectService` com novos métodos
2. Refatorar controller para delegar
3. Executar testes

### Fase D: AnalysisService (Futuro)
1. Expandir `AnalysisService` com processamento
2. Refatorar controller para delegar
3. Executar testes

---

## Decisões de Design

### 1. ModelService: Novo Serviço

**Justificativa**:
- WeightManager é muito baixo nível (apenas paths)
- Precisa de serviço que coordene:
  - Seleção de peso
  - Conversão OpenVINO
  - Setup de detector
  - Configuração de parâmetros

**Interface Proposta**:
```python
class ModelService:
    def __init__(self, weight_manager: WeightManager):
        self.weight_manager = weight_manager
        
    def convert_to_openvino(self, weight_name: str) -> bool:
        """Convert weight to OpenVINO format."""
        
    def setup_detector(self, weight_name: str, plugin_name: str, use_openvino: bool):
        """Setup detector with specified configuration."""
        
    def update_parameters(self, params: dict):
        """Update detector parameters."""
```

### 2. Manter Coordenação no MainViewModel

O MainViewModel ainda coordena serviços, mas delega execução:

```python
# ANTES (5 linhas de lógica)
def convert_active_weight_to_openvino(self, dialog):
    self.view.set_status("Convertendo...")
    self.view.update_idletasks()
    self.weight_manager.convert_to_openvino(self.active_weight_name)
    self.update_openvino_status(dialog)

# DEPOIS (1 linha + callbacks UI)
def convert_active_weight_to_openvino(self, dialog):
    self.view.set_status("Convertendo...")
    success = self.model_service.convert_to_openvino(self.active_weight_name)
    self.update_openvino_status(dialog)
```

### 3. Progressão Gradual

- ✅ Não quebrar código existente
- ✅ Manter testes passando
- ✅ Refatorar incrementalmente
- ✅ Documentar cada mudança

---

## Métricas de Sucesso

### Código
- ❌ Linhas no MainViewModel: 5705 (atual)
- 🎯 Linhas no MainViewModel: <3000 (meta)
- 🎯 Redução: ~2700 linhas (~47%)

### Arquitetura
- 🎯 Serviços bem definidos: ModelService, ProjectService, AnalysisService
- 🎯 MainViewModel: Apenas coordenação + estado UI
- 🎯 Cobertura de testes: Manter 100%

### Manutenibilidade
- 🎯 Facilitar adição de novos detectores
- 🎯 Facilitar mudanças em formato de projeto
- 🎯 Facilitar paralelização de análise

---

## Próxima Ação Concreta

**AGORA**: Criar `ModelService` stub e começar refatoração

1. Criar `src/zebtrack/core/model_service.py`
2. Implementar estrutura básica
3. Mover método `convert_to_openvino`
4. Atualizar MainViewModel para delegar
5. Executar testes

**DEPOIS**: Continuar com outros métodos de ModelService

---

## Conclusão

Esta abordagem incremental garante que:
- ✅ Testes continuam passando
- ✅ Funcionalidade não quebra
- ✅ Progresso é mensurável
- ✅ Reversões são fáceis se necessário

**Status**: Pronto para implementar ModelService
