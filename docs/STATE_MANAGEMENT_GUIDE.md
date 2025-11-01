# Guia de Gerenciamento de Estado - ZebTrack-AI

## Visão Geral

O ZebTrack-AI implementa um **fluxo de dados unidirecional** baseado em **StateManager** (fonte única da verdade) e **EventBus** (comunicação desacoplada). Esta arquitetura garante previsibilidade, testabilidade e evita bugs de sincronização entre UI e modelo.

## Princípio Fundamental: Fluxo Unidirecional

```
┌──────────────────────────────────────────────────────────────┐
│                      FLUXO DE DADOS                          │
│                                                              │
│  UI (View)  ──evento──►  EventBus  ──notifica──►  ViewModel │
│      ▲                                                  │    │
│      │                                                  ▼    │
│      │                                          StateManager │
│      │                                           (atualiza)  │
│      │                                                  │    │
│      └──────────────────  notifica mudança  ◄───────────┘    │
│                         (via callbacks)                      │
└──────────────────────────────────────────────────────────────┘
```

### Regra de Ouro

**❌ A UI NUNCA lê estado diretamente do StateManager ou ProjectManager**

**✅ A UI apenas:**
1. Emite eventos via `EventBus`
2. Recebe atualizações via callbacks registrados no `StateManager`

## Componentes da Arquitetura

### 1. StateManager (Fonte Única da Verdade)

O `StateManager` (`src/zebtrack/core/state_manager.py`) é responsável por:

- Armazenar o estado imutável da aplicação
- Notificar observadores quando o estado muda
- Garantir thread-safety com `threading.RLock()`

**Características principais:**

```python
class StateManager:
    def __init__(self):
        self._state = {}
        self._observers = []
        self._lock = threading.RLock()
    
    def update_state(self, **updates):
        """Atualiza estado e notifica observadores."""
        with self._lock:
            self._state.update(updates)
            self._notify_observers()
    
    def register_observer(self, callback):
        """Registra callback para receber notificações."""
        self._observers.append(callback)
    
    def get_project_state(self):
        """Retorna cópia imutável do estado."""
        with self._lock:
            # Cópia superficial do dict, mas project_data é deep copy
            return self._state.copy()
```

**Imutabilidade Seletiva (FASE 4):**

- `get_project_state()` retorna uma **cópia superficial** do dicionário de estado
- `project_data` dentro do estado é uma **cópia profunda** (`copy.deepcopy()`)
- Isso permite leitura eficiente de campos simples (strings, booleanos) sem copiar tudo
- Garante que modificações acidentais em `project_data` não afetem o estado interno

### 2. EventBus (Comunicação Desacoplada)

O `EventBus` (`src/zebtrack/ui/event_bus.py`) desacopla a UI do ViewModel:

```python
class EventBus:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._subscribers = {}
    
    def emit(self, event_type: str, data: Any = None):
        """UI emite evento sem conhecer quem vai processar."""
        if not self._enabled:
            return
        
        for callback in self._subscribers.get(event_type, []):
            callback(data)
    
    def subscribe(self, event_type: str, callback):
        """ViewModel se inscreve para receber eventos."""
        self._subscribers.setdefault(event_type, []).append(callback)
```

**Uso na UI:**

```python
class VideoDisplayWidget(ttk.Frame):
    def __init__(self, parent, event_bus: EventBus):
        super().__init__(parent)
        self.event_bus = event_bus
    
    def _on_play_button_clicked(self):
        # UI não conhece a lógica de processamento
        self.event_bus.emit("video.play_requested", data=None)
```

**Uso no ViewModel:**

```python
class MainViewModel:
    def __init__(self, event_bus: EventBus, state_manager: StateManager, ...):
        self.event_bus = event_bus
        self.state_manager = state_manager
        
        # Inscrever-se em eventos
        self.event_bus.subscribe("video.play_requested", self._handle_play_video)
    
    def _handle_play_video(self, data):
        # Executar lógica de negócio
        # ...
        # Atualizar estado
        self.state_manager.update_state(is_playing=True)
```

### 3. MainViewModel (Orquestrador)

O `MainViewModel` (`src/zebtrack/ui/main_viewmodel.py`) atua como um **controller** que:

- Recebe eventos da UI via `EventBus`
- Coordena serviços injetados (`DetectorService`, `VideoProcessingService`, etc.)
- Atualiza o `StateManager` após operações
- **NÃO interage diretamente com a UI** (apenas via callbacks do StateManager)

**Exemplo de fluxo completo:**

```python
class MainViewModel:
    def __init__(self, 
                 settings_obj: "Settings",
                 state_manager: StateManager,
                 event_bus: EventBus,
                 detector_service: DetectorService,
                 video_processing_service: VideoProcessingService,
                 project_manager: ProjectManager):
        
        self.settings = settings_obj
        self.state_manager = state_manager
        self.event_bus = event_bus
        self.detector_service = detector_service
        self.video_processing_service = video_processing_service
        self.project_manager = project_manager
        
        # Inscrever-se em eventos da UI
        self.event_bus.subscribe("project.load_requested", self._handle_load_project)
    
    def _handle_load_project(self, project_path: str):
        """Manipulador de evento: carregar projeto."""
        try:
            # 1. Chamar serviço de domínio
            project_data = self.project_manager.load_project(project_path)
            
            # 2. Inicializar detector baseado em configuração do projeto
            self.detector_service.initialize_detector(
                model_path=project_data["model_path"],
                backend=project_data["backend"]
            )
            
            # 3. Atualizar estado (StateManager notifica a UI automaticamente)
            self.state_manager.update_state(
                project_loaded=True,
                project_name=project_data["name"],
                project_data=project_data  # Deep copy feita pelo StateManager
            )
            
        except Exception as e:
            logger.error(f"Erro ao carregar projeto: {e}")
            self.state_manager.update_state(
                error_message=str(e),
                project_loaded=False
            )
```

### 4. ApplicationGUI (View Layer)

A `ApplicationGUI` (`src/zebtrack/ui/gui.py`) é o contêiner de componentes que:

- Registra callbacks no `StateManager` para receber atualizações
- Atualiza a interface quando o estado muda
- Emite eventos via `EventBus` quando o usuário interage

**Exemplo de callback de estado:**

```python
class ApplicationGUI:
    def __init__(self, root, view_model: MainViewModel, event_bus: EventBus):
        self.root = root
        self.view_model = view_model
        self.event_bus = event_bus
        
        # Registrar callback para receber atualizações de estado
        view_model.state_manager.register_observer(self._on_state_changed)
        
        # Criar componentes da UI
        self.video_display = VideoDisplayWidget(root, event_bus=event_bus)
        self.control_panel = ControlPanelWidget(root, event_bus=event_bus)
    
    def _on_state_changed(self):
        """Callback chamado quando StateManager atualiza."""
        # Obter estado imutável
        state = self.view_model.state_manager.get_project_state()
        
        # Atualizar UI baseado no estado
        if state.get("project_loaded"):
            self.control_panel.enable_processing_buttons()
            self.status_bar.set_text(f"Projeto: {state.get('project_name')}")
        
        if state.get("is_playing"):
            self.video_display.show_pause_icon()
        else:
            self.video_display.show_play_icon()
        
        if state.get("error_message"):
            messagebox.showerror("Erro", state.get("error_message"))
```

## Fluxo Completo: Exemplo de Carregamento de Projeto

1. **Usuário clica no botão "Abrir Projeto"** na UI
   ```python
   # UI emite evento
   self.event_bus.emit("project.load_requested", data="/caminho/projeto.yaml")
   ```

2. **EventBus notifica o ViewModel**
   ```python
   # MainViewModel recebe o evento
   def _handle_load_project(self, project_path: str):
       # Lógica de carregamento...
   ```

3. **ViewModel coordena serviços**
   ```python
   project_data = self.project_manager.load_project(project_path)
   self.detector_service.initialize_detector(...)
   ```

4. **ViewModel atualiza o StateManager**
   ```python
   self.state_manager.update_state(
       project_loaded=True,
       project_name=project_data["name"]
   )
   ```

5. **StateManager notifica observadores (UI)**
   ```python
   # ApplicationGUI recebe notificação via callback
   def _on_state_changed(self):
       state = self.view_model.state_manager.get_project_state()
       self.control_panel.enable_processing_buttons()
   ```

6. **UI se atualiza de forma reativa**
   - Botões de processamento são habilitados
   - Nome do projeto aparece na status bar
   - Interface reflete o novo estado

## Vantagens da Arquitetura

### 1. Previsibilidade
- O estado só muda em um local (`StateManager.update_state()`)
- A UI sempre reflete o estado atual (via callbacks)
- Não há estados inconsistentes entre UI e modelo

### 2. Testabilidade
- ViewModel pode ser testado sem UI (mock do EventBus e StateManager)
- Serviços podem ser testados isoladamente com DI
- UI pode ser testada com mock do ViewModel

**Exemplo de teste do ViewModel:**

```python
def test_load_project_updates_state():
    # Arrange: Criar mocks
    mock_state_manager = Mock(spec=StateManager)
    mock_event_bus = Mock(spec=EventBus)
    mock_project_manager = Mock(spec=ProjectManager)
    mock_project_manager.load_project.return_value = {"name": "TestProject"}
    
    view_model = MainViewModel(
        settings_obj=test_settings,
        state_manager=mock_state_manager,
        event_bus=mock_event_bus,
        project_manager=mock_project_manager,
        # ... outros mocks
    )
    
    # Act: Simular evento
    view_model._handle_load_project("/fake/path.yaml")
    
    # Assert: Verificar que estado foi atualizado
    mock_state_manager.update_state.assert_called_with(
        project_loaded=True,
        project_name="TestProject",
        project_data={"name": "TestProject"}
    )
```

### 3. Desacoplamento
- UI não conhece a lógica de negócio (apenas emite eventos)
- ViewModel não conhece a UI (apenas atualiza o estado)
- Serviços são reutilizáveis em diferentes contextos

### 4. Thread-Safety
- `StateManager` usa `threading.RLock()` para atualizações atômicas
- Workers em background podem atualizar o estado de forma segura
- UI pode ser atualizada via `root.after()` para evitar problemas de threading do Tkinter

**Exemplo de atualização thread-safe:**

```python
class ProcessingWorker(threading.Thread):
    def __init__(self, state_manager: StateManager):
        super().__init__()
        self.state_manager = state_manager
    
    def run(self):
        # Worker em thread separada
        for i in range(100):
            process_frame(i)
            
            # Atualização thread-safe do estado
            self.state_manager.update_state(
                processing_progress=i,
                current_frame=i
            )
```

## Padrões Comuns

### Padrão 1: Comando (UI → ViewModel)

```python
# UI emite comando
self.event_bus.emit("video.seek_to_frame", data={"frame_number": 100})

# ViewModel executa comando
def _handle_seek_to_frame(self, data):
    frame_number = data["frame_number"]
    self.video_source.seek(frame_number)
    self.state_manager.update_state(current_frame=frame_number)
```

### Padrão 2: Query (ViewModel → UI)

```python
# UI consulta estado via callback
def _on_state_changed(self):
    state = self.view_model.state_manager.get_project_state()
    
    # UI sempre lê do estado, nunca de variáveis locais
    if state.get("detector_initialized"):
        self.detection_panel.show()
```

### Padrão 3: Operação Assíncrona

```python
# ViewModel inicia operação em background
def _handle_start_processing(self, data):
    # Atualizar estado imediatamente
    self.state_manager.update_state(is_processing=True, progress=0)
    
    # Iniciar worker
    worker = ProcessingWorker(
        state_manager=self.state_manager,
        video_processing_service=self.video_processing_service
    )
    worker.start()
    
    # Worker atualiza o estado periodicamente
    # UI recebe notificações automaticamente via callback
```

## Antipadrões (Evite!)

### ❌ Antipadrão 1: UI lê de serviços diretamente

```python
# ❌ ERRADO
class VideoDisplayWidget:
    def update_display(self):
        # UI não deve acessar serviços diretamente
        project_data = self.view_model.project_manager.get_project_data()
        self.label.config(text=project_data["name"])
```

**✅ CORRETO:**

```python
class VideoDisplayWidget:
    def update_display(self, state):
        # UI lê do estado passado via callback
        self.label.config(text=state.get("project_name", ""))
```

### ❌ Antipadrão 2: ViewModel atualiza UI diretamente

```python
# ❌ ERRADO
class MainViewModel:
    def load_project(self, path):
        project_data = self.project_manager.load_project(path)
        # ViewModel não deve conhecer a UI
        self.app_gui.status_bar.set_text("Projeto carregado")
```

**✅ CORRETO:**

```python
class MainViewModel:
    def _handle_load_project(self, path):
        project_data = self.project_manager.load_project(path)
        # Atualizar estado; UI se atualiza via callback
        self.state_manager.update_state(
            status_message="Projeto carregado",
            project_loaded=True
        )
```

### ❌ Antipadrão 3: Mutação de estado fora do StateManager

```python
# ❌ ERRADO
class MainViewModel:
    def __init__(self, ...):
        self.current_frame = 0  # Estado duplicado!
    
    def next_frame(self):
        self.current_frame += 1  # UI não será notificada
```

**✅ CORRETO:**

```python
class MainViewModel:
    def _handle_next_frame(self, data):
        state = self.state_manager.get_project_state()
        current_frame = state.get("current_frame", 0)
        
        # Atualizar estado centralizado
        self.state_manager.update_state(current_frame=current_frame + 1)
```

## Checklist para Novos Desenvolvedores

Ao adicionar uma nova funcionalidade:

- [ ] A UI emite eventos via `EventBus` (não chama ViewModel diretamente)?
- [ ] O ViewModel se inscreve em eventos (não é chamado pela UI)?
- [ ] O ViewModel atualiza o `StateManager` após operações?
- [ ] A UI registra callbacks no `StateManager` para receber atualizações?
- [ ] A UI lê estado de `get_project_state()` (não de variáveis internas do ViewModel)?
- [ ] Não há acesso direto a serviços pela UI?
- [ ] Operações assíncronas atualizam o estado via `StateManager` (thread-safe)?

## Referências

- `docs/ARCHITECTURE.md`: Visão geral da arquitetura MVVM-S
- `docs/DEPENDENCY_INJECTION_GUIDE.md`: Como injetar dependências
- `src/zebtrack/core/state_manager.py`: Implementação do StateManager
- `src/zebtrack/ui/event_bus.py`: Implementação do EventBus
- `src/zebtrack/ui/main_viewmodel.py`: Exemplo de ViewModel com 11+ eventos
- `tests/core/test_state_manager_immutability.py`: Testes de imutabilidade seletiva

---

**Última atualização:** Outubro 2025 (pós-refatoração FASE 4)
