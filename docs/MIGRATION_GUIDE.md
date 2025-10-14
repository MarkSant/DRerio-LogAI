# Guia Prático de Migração para Componentes UI

## Objetivo

Este guia fornece instruções passo a passo para migrar código inline do `ApplicationGUI` para os novos componentes modulares criados no Step 6.

## Princípios da Migração

1. **Incremental**: Migre uma tab/seção por vez
2. **Testável**: Teste cada migração antes de prosseguir
3. **Reversível**: Mantenha código legado comentado até confirmar funcionamento
4. **Event-Driven**: Use eventos ao invés de chamadas diretas ao controller

---

## Passo 1: Identificar Seção para Migrar

### Seções Candidatas (por ordem de prioridade)

1. ✅ **Zone Configuration Tab** (`_create_roi_analysis_tab`)
   - Substituir por: `VideoDisplayWidget` + `ZoneControlsWidget`
   - Complexidade: Média
   - Impacto: Alto (melhoria significativa na manutenibilidade)

2. ✅ **Analysis Tab** (`_create_analysis_tab`)
   - Substituir por: `AnalysisControlsWidget` + `VideoDisplayWidget`
   - Complexidade: Baixa
   - Impacto: Médio

3. ✅ **Main Controls** (`_create_main_controls_tab`)
   - Substituir por: `ControlPanelWidget`
   - Complexidade: Baixa
   - Impacto: Médio

4. ⏳ **Project Overview** (`_create_project_overview_panel`)
   - Substituir por: `ProjectOverviewWidget`
   - Complexidade: Média
   - Impacto: Médio

---

## Passo 2: Preparar a Migração

### 2.1 Importar Componentes

No início do `gui.py`, adicionar:

```python
from zebtrack.ui.components import (
    VideoDisplayWidget,
    ZoneControlsWidget,
    ControlPanelWidget,
    ProjectOverviewWidget,
    AnalysisControlsWidget,
)
```

### 2.2 Criar Método de Subscrição de Eventos

Criar métodos centralizados para subscrever eventos:

```python
def _subscribe_component_events(self):
    """Subscribe to all component events."""
    if not self.event_bus:
        return
    
    # Zone control events
    self._subscribe_zone_events()
    
    # Control panel events
    self._subscribe_control_events()
    
    # Analysis events
    self._subscribe_analysis_events()

def _subscribe_zone_events(self):
    """Subscribe to zone control events."""
    if not self.event_bus:
        return
    
    self.event_bus.subscribe("zone.auto_detect_clicked", 
                             lambda data: self._on_auto_detect_clicked())
    self.event_bus.subscribe("zone.draw_main_polygon", 
                             lambda data: self._start_main_arena_drawing())
    self.event_bus.subscribe("zone.draw_roi", 
                             lambda data: self._start_roi_drawing())
    # ... adicionar outros eventos
```

---

## Passo 3: Migrar Tab Individual

### Exemplo: Migrar Zone Configuration Tab

#### ANTES (código inline - ~500 linhas):

```python
def _create_roi_analysis_tab(self):
    """Creates the tab for ROI and detection zone configuration."""
    self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")
    
    # ... 500+ linhas criando widgets inline
    
    # Canvas
    self.roi_canvas = Canvas(self.viz_frame, bg="gray")
    self.roi_canvas.pack(expand=True, fill="both")
    
    # Botões
    actions_frame = ttk.LabelFrame(...)
    ttk.Button(actions_frame, text="Detectar Aquário", command=self._on_auto_detect_clicked)
    # ... mais 400 linhas
```

#### DEPOIS (usando componentes - ~50 linhas):

```python
def _create_roi_analysis_tab(self):
    """Creates the tab for ROI and detection zone configuration."""
    self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")
    
    # Layout: controles (esquerda) + display (direita)
    main_pane = ttk.PanedWindow(self.zone_tab_frame, orient="horizontal")
    main_pane.pack(expand=True, fill="both")
    
    # Painel de controles (esquerda)
    left_panel = ttk.Frame(main_pane, padding=5, relief="groove", borderwidth=2)
    main_pane.add(left_panel, weight=1)
    
    self.zone_controls = ZoneControlsWidget(
        left_panel,
        event_bus=self.event_bus
    )
    self.zone_controls.pack(fill="both", expand=True)
    
    # Painel de visualização (direita)
    right_panel = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
    main_pane.add(right_panel, weight=4)
    
    self.video_display = VideoDisplayWidget(
        right_panel,
        event_bus=self.event_bus,
        width=800,
        height=600,
        bg="gray"
    )
    self.video_display.pack(fill="both", expand=True)
    
    # Configurar posição inicial do divisor
    main_pane.after(10, lambda: main_pane.sashpos(0, 420))
    
    # Subscrever eventos dos componentes
    self._subscribe_zone_events()
```

---

## Passo 4: Mapear Funcionalidades Existentes

### 4.1 Mapeamento de Widgets

| Widget Antigo (inline) | Componente Novo | Método de Acesso |
|------------------------|-----------------|------------------|
| `self.roi_canvas` | `self.video_display` | `.canvas` |
| `self.zone_listbox` | `self.zone_controls` | `.zone_listbox` |
| `self.draw_roi_button` | `self.zone_controls` | `.draw_roi_button` |
| `self.roi_template_combobox` | `self.zone_controls` | `.roi_template_combobox` |
| `self.start_rec_btn` | `self.control_panel` | `.start_rec_btn` |
| `self.stop_rec_btn` | `self.control_panel` | `.stop_rec_btn` |
| `self.analysis_video_label` | `self.analysis_controls` | `.analysis_video_label` |
| `self.track_selector_widget` | `self.analysis_controls` | `.track_selector_widget` |

### 4.2 Mapeamento de Métodos

| Método Antigo | Componente | Método Novo |
|---------------|------------|-------------|
| `self._draw_bg_image_to_canvas()` | `video_display` | `.set_image(image)` ou `.load_frame(path, frame)` |
| `self._video_to_canvas(x, y)` | `video_display` | `.video_to_canvas(x, y)` |
| `self._canvas_to_video(x, y)` | `video_display` | `.canvas_to_video(x, y)` |
| `self._populate_video_selector_tree()` | `zone_controls` | Interno (ou emitir evento para refresh) |
| `self._refresh_roi_templates()` | `zone_controls` | `.update_template_list(templates)` |

---

## Passo 5: Adaptar Event Handlers

### Pattern: Converter comando direto em event handler

#### ANTES:
```python
ttk.Button(parent, text="Detectar", command=self._on_auto_detect_clicked)

def _on_auto_detect_clicked(self):
    frames = int(self.stabilization_frames_var.get())
    self.controller.auto_detect_arena(frames)
```

#### DEPOIS:
```python
# No componente (zone_controls.py):
ttk.Button(parent, text="Detectar", command=self._on_auto_detect_clicked)

def _on_auto_detect_clicked(self):
    self.emit_event("zone.auto_detect_clicked", {
        "stabilization_frames": int(self.stabilization_frames_var.get())
    })

# No ApplicationGUI:
def _subscribe_zone_events(self):
    self.event_bus.subscribe("zone.auto_detect_clicked", self._handle_auto_detect)

def _handle_auto_detect(self, data: dict):
    frames = data["stabilization_frames"]
    self.controller.auto_detect_arena(frames)
```

---

## Passo 6: Atualizar State Management

### Usar APIs Públicas dos Componentes

#### ANTES:
```python
# Estado espalhado pela GUI
if self.draw_roi_button:
    self.draw_roi_button.config(state="normal")
if self.toggle_view_btn:
    self.toggle_view_btn.config(state="disabled")
```

#### DEPOIS:
```python
# API centralizada no componente
self.zone_controls.set_draw_roi_enabled(True)
self.zone_controls.set_toggle_view_enabled(False)
```

---

## Passo 7: Testar a Migração

### Checklist de Testes

- [ ] A tab renderiza corretamente
- [ ] Todos os botões são clicáveis
- [ ] Eventos são emitidos corretamente
- [ ] Eventos são recebidos e processados
- [ ] Estado dos widgets atualiza corretamente
- [ ] Não há erros no console
- [ ] Funcionalidade original preservada

### Comando de Teste:
```bash
poetry run python -m zebtrack
# Navegar até a tab migrada e testar todas as funcionalidades
```

---

## Passo 8: Limpar Código Legado

### Após Confirmar Funcionamento:

1. **Remover código inline comentado**
2. **Remover imports não utilizados**
3. **Remover atributos obsoletos** (`self.roi_canvas` → usar `self.video_display.canvas`)
4. **Atualizar testes** que referenciam widgets antigos

---

## Troubleshooting

### Problema: Componente não aparece na tela

**Solução**: Verificar se `.pack()` ou `.grid()` foi chamado:
```python
self.zone_controls.pack(fill="both", expand=True)
```

### Problema: Eventos não são recebidos

**Solução**: Verificar se event bus foi passado e subscrito:
```python
# No componente
self.emit_event("event.name", data)  # ✅

# No ApplicationGUI
self.event_bus.subscribe("event.name", handler)  # ✅
```

### Problema: Widget interno não acessível

**Solução**: Usar atributo público do componente:
```python
# ❌ Não funciona (widget interno)
self.roi_canvas.delete("all")

# ✅ Usar componente
self.video_display.canvas.delete("all")
# Ou melhor:
self.video_display.clear()
```

---

## Exemplo Completo: Migration PR Template

```markdown
## Migração de [Nome da Tab] para Componentes UI

### Alterações

- ✅ Substituído código inline por `[ComponentName]Widget`
- ✅ Adicionadas subscrições de eventos
- ✅ Atualizado state management para usar API pública
- ✅ Removido código legado após testes

### Métricas

- **Linhas removidas**: ~XXX
- **Linhas adicionadas**: ~XX
- **Redução de complexidade**: XX%

### Testes Realizados

- [x] Tab renderiza corretamente
- [x] Funcionalidades preservadas
- [x] Eventos funcionando
- [x] Sem regressões

### Próximos Passos

- [ ] Migrar [Próxima Tab]
- [ ] Adicionar testes de integração
- [ ] Atualizar documentação de usuário
```

---

## Referências

- **Componentes**: `src/zebtrack/ui/components/`
- **Exemplo de Integração**: `src/zebtrack/ui/integration_example.py`
- **Documentação**: `docs/UI_COMPONENT_ARCHITECTURE.md`
- **Testes**: `tests/ui/test_components.py`

---

## Contato

Para dúvidas ou sugestões sobre a migração, consultar:
- Documentação do Step 6: `docs/STEP6_UI_COMPONENTS_SUMMARY.md`
- Código-fonte dos componentes com docstrings detalhadas
