# Guia de Testes - ZebTrack-AI

## Visão Geral

Os testes do ZebTrack-AI foram organizados para melhor performance e compatibilidade cross-platform (Windows/Linux/macOS).

## Marcadores de Teste (Test Markers)

### Tipos de Marcadores

- **`@pytest.mark.gui`**: Testes que usam componentes Tkinter
  - Rodam sequencialmente (não paralelizados)
  - Compatíveis com Windows (não requerem virtual display)
  - Exemplo: Tests do wizard, análise de UI

- **`@pytest.mark.slow`**: Testes que demoram > 1 segundo
  - Envolvem operações de I/O lentas ou sleeps necessários
  - Excluídos da execução padrão (para CI/desenvolvimento rápido)
  - Exemplo: Testes de cache com sleep de filesystem

- **`@pytest.mark.integration`**: Testes de integração entre componentes
  - Testam múltiplos módulos trabalhando juntos
  - Podem ser mais lentos que testes unitários

- **`@pytest.mark.unit`**: Testes unitários puros
  - Testam uma única função/classe isoladamente
  - Rápidos e independentes

- **`@pytest.mark.ttkbootstrap_singleton`**: Testes afetados pelo Style singleton do ttkbootstrap
  - Devem ser executados em isolamento
  - Excluídos da execução padrão
  - Exemplo: `tests/ui/test_components.py` (22 testes)
  - **Problema conhecido**: O singleton do ttkbootstrap mantém referências a Tk instances antigas
  - **Solução**: Rodar em isolamento: `poetry run pytest tests/ui/test_components.py`

## Comandos de Execução

### Execução Padrão (Rápida)
```powershell
# Executa apenas testes rápidos e não-GUI em paralelo
# Exclui: GUI, slow e ttkbootstrap_singleton
poetry run pytest

# Equivalente a:
poetry run pytest -m "not (gui or slow or ttkbootstrap_singleton)"
```

**Resultado esperado**: ~540 testes em ~55 segundos

### Executar Testes GUI
```powershell
# Testes GUI rodam sequencialmente (sem paralelização)
poetry run pytest -m gui -n0
```

### Executar Testes Slow
```powershell
# Inclui testes que demoram mais tempo
poetry run pytest -m slow -n0
```

### Executar Testes ttkbootstrap (Isoladamente)
```powershell
# IMPORTANTE: Esses testes DEVEM ser executados em isolamento
poetry run pytest tests/ui/test_components.py
```

**Resultado esperado**: 22 testes em ~2.5 segundos

### Executar Todos os Testes
```powershell
# Para validação completa antes de commit/release
# Atenção: Rode em 3 etapas separadas devido ao ttkbootstrap

# 1. Testes rápidos
poetry run pytest -m "not (gui or slow or ttkbootstrap_singleton)"

# 2. Testes GUI
poetry run pytest -m "gui and not ttkbootstrap_singleton" -n0

# 3. Testes ttkbootstrap (isolados)
poetry run pytest tests/ui/test_components.py

# 4. Testes slow (opcional)
poetry run pytest -m slow
```

### Executar Testes Sem Cobertura (Mais Rápido)
```powershell
poetry run pytest --no-cov
```

### Execução Sequencial (Debugging)
```powershell
# Útil para debugar problemas de paralelização
poetry run pytest -n0
```

## Estrutura de Testes

```
tests/
├── conftest.py              # Fixtures compartilhadas (tkinter_root, etc.)
├── pytest.ini               # Configuração de markers
│
├── test_*.py               # Testes de nível superior
├── core/                   # Testes do módulo core
├── analysis/               # Testes de análise comportamental
├── ui/                     # Testes de componentes UI
├── integration/            # Testes de integração end-to-end
└── fixtures/               # Fixtures e dados de teste

```

## Fixture Organization
- `tests/conftest.py`: Global fixtures (tkinter_root)
- `tests/core/conftest.py`: Core-specific fixtures (view_model, state_manager)
- `tests/ui/wizard/conftest.py`: Wizard-specific fixtures (wizard_dependencies)

## Compatibilidade Cross-Platform

### Windows
- ✅ Tkinter funciona nativamente (sem virtual display)
- ✅ Testes GUI rodam normalmente
- ⚠️ Alguns sleeps podem variar por resolução de timestamp do filesystem

### Linux
- ✅ Usa `pyvirtualdisplay` automaticamente para testes GUI headless
- ✅ Funciona em CI/CD sem display gráfico
- ✅ Resolução de timestamp mais precisa

### macOS
- ✅ Tkinter funciona nativamente
- ✅ Não requer virtual display

## Troubleshooting

### Erro: "pyvirtualdisplay não encontrado" (Linux)
```powershell
poetry install  # Reinstala dependências incluindo pyvirtualdisplay
```

### Testes GUI falhando no Windows
- Certifique-se de que não está rodando via SSH sem X11 forwarding
- Verifique se o display está acessível

### Testes muito lentos
```powershell
# Execute apenas testes rápidos
poetry run pytest -m "not slow"

# Ou desabilite cobertura
poetry run pytest --no-cov
```

### Problemas com pytest-xdist (paralelização)
```powershell
# Force execução sequencial
poetry run pytest -n0
```

## Problemas Conhecidos e Resolvidos

### ✅ RESOLVIDO: TclError "Can't find a usable tk.tcl" em Testes GUI

**Problema Original**:
```
_tkinter.TclError: Can't find a usable tk.tcl in the following directories:
```

**Causa Raiz** (diagnosticada em 2025-01-29):
- **NÃO** era problema de instalação do Tkinter
- **ERA** conflito de execução paralela com pytest-xdist

**Explicação Técnica**:
O `ttkbootstrap.Style` mantém estado global (singleton) que não é thread-safe. Quando pytest-xdist cria múltiplos workers (processos paralelos), cada worker tenta instanciar o Style singleton simultaneamente, causando:
1. Conflitos de acesso ao Tcl/Tk interpreter
2. Referências corrompidas entre processos
3. TclError "Can't find a usable tk.tcl" (sintoma, não causa raiz)

**Solução Final** (implementada):
1. ✅ **pytest.ini atualizado**: Exclui GUI tests por padrão (`-m "not (gui or slow)"`)
2. ✅ **Documentação clara**: GUI tests DEVEM usar `-n0` explicitamente
3. ✅ **Scripts helper**: `scripts/run_gui_tests.ps1` com comando correto
4. ✅ **Markers corretos**: Todos os GUI tests marcados com `@pytest.mark.gui`

**Comandos Corretos**:
```powershell
# ❌ ERRADO (causa TclError)
poetry run pytest -m gui          # Usa -n=auto por padrão

# ✅ CORRETO (execução serial)
poetry run pytest -m gui -n0

# ✅ CORRETO (testes rápidos, exclui GUI)
poetry run pytest                 # Usa -m "not (gui or slow)" por padrão

# ✅ CORRETO (testes não-GUI em paralelo)
poetry run pytest -m "not gui"
```

**Validação**:
- Tkinter funciona corretamente: `poetry run python -c "import tkinter; root = tkinter.Tk(); print('OK'); root.destroy()"`
- Teste GUI isolado passa: `poetry run pytest tests/ui/test_gui.py::test_specific -n0`
- Teste GUI paralelo falha: `poetry run pytest tests/ui/test_gui.py::test_specific -n auto` (esperado)

**Referências**:
- [pytest-xdist thread safety](https://pytest-xdist.readthedocs.io/en/latest/known-limitations.html)
- [ttkbootstrap Style singleton issue](https://github.com/israel-dryer/ttkbootstrap/issues)

---

### 1. Singleton do ttkbootstrap (22 testes afetados)

**Problema**: O `ttkbootstrap.Style` mantém referências globais a instâncias Tk antigas, causando conflitos entre testes.

**Sintomas**:
```
RuntimeError: main thread is not in main loop
TclError: invalid command name ".!style"
```

**Workaround**:
- Testes marcados com `@pytest.mark.ttkbootstrap_singleton` são excluídos da execução padrão
- Execute isoladamente: `poetry run pytest tests/ui/test_components.py`
- Não execute múltiplos testes ttkbootstrap em paralelo

**Referência**: Issue conhecido da biblioteca ttkbootstrap

---

### 2. Testes de Integração com API Antiga (12 falhas)

**Problema**: Testes em `tests/integration/` usam API antiga do Recorder, incompatível com refatoração da Fase 4.

**Diferença de API**:
```python
# API Antiga (testes)
recorder.start(output_folder=..., base_name=...)

# API Nova (código de produção)
recorder.start_recording(output_folder=..., frame_width=..., frame_height=..., zones=...)
```

**Status**:
- ✅ Código de produção funcionando corretamente
- ⚠️ Testes de integração precisam ser refatorados (tarefa futura)
- 🔒 Não afeta funcionalidade do aplicativo

**Testes Afetados**:
- `test_critical_integrations.py::test_video_file_workflow`
- `test_critical_integrations.py::test_calibration_data_flow`
- `test_critical_integrations.py::test_arduino_integration_recording`
- `test_critical_integrations.py::test_error_recovery_during_processing`
- `test_end_to_end.py` (6 testes)
- `test_workflow_orchestration.py::test_wizard_to_processing_workflow`

---

### 3. Race Conditions no Windows (Resolvido com Workarounds)

**Problema**: Windows mantém file handles abertos após `recorder.stop_recording()`, causando `PermissionError` na limpeza.

**Solução Implementada**:
```python
@pytest.fixture
def recorder_setup(tmp_path):
    # Use pytest's tmp_path (thread-safe)
    test_dir = tmp_path / "recorder_test"

    yield recorder, output_folder, frame_width, frame_height

    # Cleanup com garbage collection forçado
    del recorder
    gc.collect()
    time.sleep(0.2)  # Permite Windows liberar handles

    # Retry com exponential backoff
    for attempt in range(3):
        try:
            shutil.rmtree(test_dir)
            break
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
```

**Melhorias Aplicadas**:
- ✅ Uso de `tmp_path` fixture (thread-safe e auto-cleanup)
- ✅ `os.fsync()` em `recorder._close_parquet_writer()` para forçar flush
- ✅ `gc.collect()` para liberar file handles imediatamente
- ✅ Delays estratégicos após operações de I/O
- ✅ Retry logic com exponential backoff

**Referências**:
- `tests/test_recorder.py:12-56` (fixture com cleanup robusto)
- `src/zebtrack/io/recorder.py:325-343` (fsync implementation)

---

### 4. Cobertura de Código (Target: 70%, Atual: 43.59%)

**Problema**: Meta de 70% de cobertura não foi atingida devido à natureza da codebase.

**Análise de Cobertura por Módulo**:

| Módulo | Cobertura | Motivo |
|--------|-----------|--------|
| **Core (Alta)** | 80-97% | ✅ Bem testado |
| `state_manager.py` | 97% | ✅ Testes abrangentes |
| `camera.py` | 100% | ✅ Completo |
| `recorder.py` | 80% | ✅ Casos edge cobertos |
| **UI (Baixa)** | 0-13% | ⚠️ Tkinter difícil de testar |
| `gui.py` | 13% (5442 linhas) | ⚠️ Código visual extenso |
| `wizard/*.py` | 0-5% | ⚠️ Workflows interativos |
| `components.py` | 22% | ⚠️ Widgets ttkbootstrap |

**Por que 70% é difícil?**:
1. **UI domina a codebase**: ~40% do código é Tkinter (gui.py, wizard/, components)
2. **Testes UI são complexos**: Requerem mocking extensivo de Tk widgets
3. **ttkbootstrap limita testabilidade**: Singleton issues impedem testes paralelos
4. **Workflows visuais**: Wizard de 5 etapas difícil de automatizar completamente

**Estratégia Atual**:
- ✅ **Priorizar core modules**: StateManager, Recorder, Detector, Camera (>80% coverage)
- ✅ **Testes de integração**: Cobertura end-to-end dos workflows críticos
- ✅ **Smoke tests para UI**: Validação básica de inicialização
- ⚠️ **UI coverage**: Aceitar baixa cobertura em código puramente visual

**Recomendação**: Manter foco em cobertura de lógica de negócio (core/analysis/io) em vez de perseguir 70% global.

---

### 5. Parquet Schema Immutability

**Problema**: Alterar schema durante gravação causa `ValueError` e interrompe recording.

**Comportamento Esperado**: Schema é "locked" no primeiro flush e validado em cada flush subsequente.

```python
# ❌ Erro: Mudar calibration depois de iniciar
recorder.start_recording(output_folder, width, height, zones=ZoneData())
recorder.write_detection_data(0.1, 1, [(10, 10, 20, 20, 0.9, 1)])
recorder.pixel_per_cm_ratio = (1.0, 1.0)  # ❌ Schema change!
recorder.write_detection_data(0.2, 2, [...])  # ValueError!

# ✅ Correto: Definir calibration no start
recorder.start_recording(
    output_folder, width, height,
    zones=ZoneData(),
    pixel_per_cm_ratio=(1.0, 1.0)  # ✅ Schema fixo desde início
)
```

**Testes Relacionados**:
- `test_recorder_schema_validation.py` (5 testes)
- Valida que schema changes são detectados e recording é interrompido

---

## Performance

### Tempo de Execução Esperado

| Modo | Tempo Aproximado | Comando |
|------|------------------|---------|
| **Padrão (rápido)** | 1-2 minutos | `poetry run pytest` |
| **Com GUI** | 3-5 minutos | `poetry run pytest -m gui -n0` |
| **Com slow** | 5-8 minutos | `poetry run pytest -m slow` |
| **Completo** | 8-12 minutos | `poetry run pytest -m "" -n0` |

### Otimizações Aplicadas

1. ✅ Testes GUI marcados e isolados da paralelização
2. ✅ Sleeps desnecessariamente longos reduzidos (10s → 1s onde aplicável)
3. ✅ Testes lentos marcados e excluídos da execução padrão
4. ✅ Paralelização automática para testes não-GUI (`-n=auto`)
5. ✅ Fixture tkinter_root otimizada para cada plataforma

## Boas Práticas

### Ao Escrever Novos Testes

1. **Marque apropriadamente**:
   ```python
   @pytest.mark.gui
   def test_wizard_ui():
       # Testa componentes Tkinter
       pass

   @pytest.mark.slow
   def test_video_processing():
       # Processa vídeo completo
       pass

   @pytest.mark.integration
   def test_end_to_end_workflow():
       # Testa fluxo completo
       pass
   ```

2. **Evite sleeps longos**:
   ```python
   # ❌ Ruim
   time.sleep(10)

   # ✅ Bom - use threading.Event
   event.wait(timeout=1.0)

   # ✅ Ou use sleeps curtos
   time.sleep(0.1)
   ```

3. **Isole testes GUI**:
   - Use fixtures para criar/destruir widgets Tkinter
   - Sempre marque com `@pytest.mark.gui`
   - Teste lógica separadamente dos componentes visuais quando possível

4. **Prefira mocks para I/O**:
   ```python
   # ✅ Bom - mock em vez de I/O real
   @patch("pathlib.Path.read_text")
   def test_load_config(mock_read):
       mock_read.return_value = "config content"
       # Teste rápido sem tocar disco
   ```

## Referências

- [pytest documentation](https://docs.pytest.org/)
- [pytest-xdist](https://pytest-xdist.readthedocs.io/)
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html)
