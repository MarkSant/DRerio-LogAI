# Fase 3: AnalysisService Expansion - Plano Estratégico

**Data**: 14 de Outubro de 2025  
**Status**: 📋 **PLANEJAMENTO EM ANDAMENTO**  
**Potencial**: 🎯 **300-500 linhas de redução**

---

## 📊 Situação Atual

### MainViewModel Status
- **Linhas atuais**: 4,870
- **Meta**: < 3,000 linhas
- **Faltam**: 1,870 linhas (38.4%)
- **Progresso acumulado**: 835 linhas removidas (-14.6%)

### AnalysisService Existente
- **Arquivo**: `src/zebtrack/analysis/analysis_service.py`
- **Linhas**: 332
- **Responsabilidade atual**: Orquestração de análise comportamental + ROI
- **Métodos principais**: `run_full_analysis()`, `load_trajectory_with_inference()`, etc.

---

## 🎯 Métodos Identificados para Extração

### 1. **Processamento de Vídeos** (~524 linhas!)

#### `_process_videos()` - Linha 5112-5635 (~524 linhas)
**Responsabilidades**:
- Loop principal de processamento em batch
- Gerenciamento de UI durante processamento
- Coordenação de perfis de análise
- Tratamento de cancelamento
- Atualização de progresso

**Complexidade**: MUITO ALTA
- 524 linhas em um único método
- Lógica entrelaçada: UI + processamento + state management
- Múltiplos callbacks e context building

**Potencial de extração**: 300-400 linhas

---

### 2. **Processamento de Vídeo Individual** (~100-150 linhas)

#### `_process_single_video()` - Linha 4720
**Responsabilidades**:
- Processar um vídeo completo
- Gerenciar zona ativa
- Coordenar tracking + análise
- Resolver caminhos de resultados
- Callbacks de progresso

**Complexidade**: ALTA
- Coordena múltiplos subsistemas
- Tracking → Analysis pipeline
- Metadata resolution
- Arena polygon handling

**Potencial de extração**: 80-120 linhas

---

### 3. **Helpers de Processamento** (~100-150 linhas combinadas)

#### `_determine_processing_intervals()` - Linha 4032
- Resolve intervalos de análise/display
- Lê configuração de projeto/single-video
- ~30-40 linhas

#### `_prepare_processing_ui()` - Linha 4118
- Prepara UI para processamento
- Atualiza contadores/status
- ~25-35 linhas

#### `_build_metadata_context()` - Linha 4153
- Constrói contexto de metadata
- Extrai group/day/subject
- ~40-60 linhas

**Potencial de extração**: 100-150 linhas combinadas

---

### 4. **Métodos Auxiliares** (identificação pendente)

Outros métodos relacionados a processamento que precisam ser mapeados:
- `_run_tracking_if_needed()`
- `_run_analysis_pipeline()`
- `_compose_analysis_view_metadata()`
- `_resolve_results_path()`
- `_make_progress_callback()`
- `_display_initial_frame()`
- `_notify_task_status_start()`
- `apply_project_settings_to_batch()`

**Estimativa**: Mais 150-200 linhas

---

## 📈 Potencial Total de Redução

| Categoria | Linhas | Prioridade |
|-----------|--------|------------|
| `_process_videos()` | ~400 | 🔴 CRÍTICA |
| `_process_single_video()` | ~100 | 🟡 ALTA |
| Helpers principais | ~100 | 🟡 ALTA |
| Métodos auxiliares | ~150 | 🟢 MÉDIA |
| **TOTAL ESTIMADO** | **~750 linhas** | - |

**Meta conservadora**: 300-400 linhas  
**Meta agressiva**: 500-750 linhas

---

## 🏗️ Arquitetura Proposta

### Opção A: Expandir AnalysisService (Recomendada)

**Estrutura**:
```python
class AnalysisService:
    # Métodos existentes (332 linhas)
    def run_full_analysis(...)
    def load_trajectory_with_inference(...)
    
    # NOVOS métodos (Phase 3 expansion)
    def process_videos_batch(...)           # Extrai _process_videos
    def process_single_video(...)           # Extrai _process_single_video
    def prepare_processing_context(...)     # Extrai helpers
    def determine_intervals(...)            # Extrai _determine_processing_intervals
    def build_metadata_context(...)         # Extrai _build_metadata_context
    
    # Métodos privados auxiliares
    def _run_tracking(...)
    def _run_analysis_pipeline(...)
    def _resolve_output_path(...)
```

**Vantagens**:
- ✅ Consolidação em um único serviço
- ✅ AnalysisService torna-se "one-stop-shop" para análise
- ✅ Reduz acoplamento com MainViewModel
- ✅ Facilita testes isolados

**Desvantagens**:
- ⚠️ AnalysisService ficará grande (~800-1000 linhas)
- ⚠️ Pode precisar quebrar em sub-services posteriormente

---

### Opção B: Criar ProcessingService Separado

**Estrutura**:
```python
# Novo arquivo: src/zebtrack/core/processing_service.py
class ProcessingService:
    def __init__(self, controller, analysis_service):
        self.controller = controller
        self.analysis_service = analysis_service
    
    def process_videos_batch(...)
    def process_single_video(...)
    # ...helpers
```

**Vantagens**:
- ✅ Separação clara: ProcessingService (orquestração) vs AnalysisService (análise)
- ✅ Services menores e mais focados
- ✅ Mais fácil testar isoladamente

**Desvantagens**:
- ⚠️ Mais arquivos para manter
- ⚠️ Dependência entre ProcessingService → AnalysisService
- ⚠️ Pode criar confusão sobre onde colocar nova lógica

---

## 🎯 Recomendação: Opção A (Expandir AnalysisService)

**Razões**:
1. AnalysisService **JÁ EXISTE** com estrutura sólida
2. Processamento é **parte integrante** da análise
3. Reduz número de abstrações desnecessárias
4. Mais fácil para desenvolvedores encontrarem lógica de análise
5. Se ficar muito grande (~1000 linhas), podemos quebrar depois

---

## 📋 Plano de Implementação (Fase 3)

### **Etapa 1: Análise Detalhada** (1-2h)
- [ ] Ler todos os métodos de processamento completamente
- [ ] Mapear dependências (detector, recorder, UI callbacks)
- [ ] Identificar pontos de acoplamento com MainViewModel
- [ ] Documentar fluxo de dados completo

### **Etapa 2: Design da Expansão** (30min - 1h)
- [ ] Definir assinaturas de métodos públicos
- [ ] Projetar injeção de dependências (detector, recorder, etc.)
- [ ] Definir estratégia de UI callbacks
- [ ] Planejar compatibilidade com ProcessingWorker existente

### **Etapa 3: Implementação Incremental** (3-5h)
1. **Extrair helpers simples primeiro** (~1h)
   - `_determine_processing_intervals()`
   - `_build_metadata_context()`
   - `_prepare_processing_ui()`

2. **Extrair _process_single_video** (~1-2h)
   - Método médio, menos dependências
   - Testar isoladamente

3. **Extrair _process_videos** (~2-3h)
   - Método mais complexo
   - Requer integração com ProcessingWorker
   - Mais callbacks UI

### **Etapa 4: Refatoração do MainViewModel** (1-2h)
- [ ] Simplificar métodos para delegar ao AnalysisService
- [ ] Remover métodos privados extraídos
- [ ] Manter apenas coordenação de alto nível

### **Etapa 5: Testes & Validação** (1-2h)
- [ ] Executar suite completa (508 testes)
- [ ] Verificar testes de integração de processamento
- [ ] Validar contagem de linhas (~4,470-4,570)
- [ ] Testar workflows end-to-end (single video, batch)

**Tempo total estimado**: 6-12 horas

---

## ⚠️ Riscos & Mitigações

### Risco 1: Quebrar ProcessingWorker
**Probabilidade**: 🟡 Média  
**Impacto**: 🔴 Alto

**Mitigação**:
- Manter interface de `ProcessingWorker` intacta
- AnalysisService fornece métodos que `ProcessingWorker` chama
- Testar com single video E batch workflows

### Risco 2: UI Callbacks Complexos
**Probabilidade**: 🟡 Média  
**Impacto**: 🟡 Médio

**Mitigação**:
- Usar padrão de callback injection (como RecordingService)
- Métodos `set_ui_callbacks()` para injetar wrappers
- Manter `_schedule_on_ui()` no controller

### Risco 3: Dependências Circulares
**Probabilidade**: 🟢 Baixa  
**Impacto**: 🔴 Alto

**Mitigação**:
- AnalysisService NÃO deve importar MainViewModel
- Usar TYPE_CHECKING para hints
- Passar detector/recorder via métodos, não __init__

### Risco 4: Testes Quebrados
**Probabilidade**: 🟡 Média  
**Impacto**: 🟡 Médio

**Mitigação**:
- Rodar testes após cada extração incremental
- Manter backward compatibility durante transição
- Usar property pattern para acesso dinâmico (como RecordingService)

---

## 📊 Impacto Esperado

### Redução de Linhas (Conservadora)
- MainViewModel: 4,870 → ~4,570 linhas (**-300, -6.2%**)
- AnalysisService: 332 → ~632 linhas (+300)
- Total do projeto: +0 linhas (apenas reorganização)

### Redução de Linhas (Agressiva)
- MainViewModel: 4,870 → ~4,370 linhas (**-500, -10.3%**)
- AnalysisService: 332 → ~832 linhas (+500)
- Total do projeto: +0 linhas (apenas reorganização)

### Benefícios Qualitativos
- ✅ MainViewModel mais simples e focado em coordenação
- ✅ AnalysisService torna-se serviço completo de análise
- ✅ Lógica de processamento isolada e testável
- ✅ Redução de complexidade ciclomática
- ✅ Mais fácil adicionar novos tipos de análise

---

## 🚀 Próximos Passos Imediatos

### Para Continuar Fase 3:
1. ✅ **Aprovar este plano estratégico**
2. Executar **Etapa 1: Análise Detalhada**
   - Ler `_process_videos()` completamente
   - Ler `_process_single_video()` completamente
   - Mapear todas as dependências
3. Criar **todo list detalhado** para implementação
4. Começar extração incremental

### Alternativa (Se Preferir Algo Mais Simples Primeiro):
Voltar para **Fase 2.3: Validation Logic** (~150-200 linhas)
- Menor risco
- Menor complexidade
- Menor impacto

---

## 📝 Decisão Necessária

**Qual caminho seguir?**

**Opção 1**: 🎯 **Continuar Fase 3 (AnalysisService Expansion)**
- Alto impacto (300-500 linhas)
- Alto risco (complexidade média-alta)
- Tempo: 6-12 horas

**Opção 2**: 🛡️ **Fase 2.3 primeiro (Validation Logic)**
- Médio impacto (150-200 linhas)
- Baixo risco
- Tempo: 2-4 horas
- Depois volta para Fase 3

**Recomendação**: **Opção 1** (Fase 3), pois tem maior impacto e é a área mais crítica.

---

**Aguardando decisão do usuário para prosseguir...**
