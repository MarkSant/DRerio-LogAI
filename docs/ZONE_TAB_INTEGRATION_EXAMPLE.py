"""
Patch de demonstração: Integração do ZoneControlsWidget na Zone Configuration Tab.

Este arquivo mostra como seria a implementação real da integração do ZoneControlsWidget
no ApplicationGUI, substituindo o código inline existente.

NOTA: Este é um patch de demonstração/documentação. A integração real deve ser feita
incrementalmente com testes entre cada mudança.
"""


def _create_roi_analysis_tab_NEW(self):
    """
    VERSÃO NOVA: Creates the tab for ROI and detection zone configuration.
    
    Substituições principais:
    - Código inline de 500+ linhas → ZoneControlsWidget + VideoDisplayWidget
    - Canvas manual → VideoDisplayWidget com scaling automático
    - Botões e controles inline → ZoneControlsWidget com eventos
    - Lógica de desenho mantida no controller (não mudou)
    """
    # Importar componentes (já feito no topo do arquivo)
    # from zebtrack.ui.components import VideoDisplayWidget, ZoneControlsWidget
    
    # Dados e estado ainda necessários (lógica de desenho)
    self.roi_data = {}
    self.drawing_mode = None
    self.current_polygon_points = []
    self.current_circle_center = None
    
    # Coordenadas para desenho (agora delegadas ao VideoDisplayWidget)
    self._poly_pts_canvas = []
    self._poly_pts_video = []
    
    # 1. Criar o frame da tab
    self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")
    
    # 2. Layout: Painel de controles (esquerda) + Visualização (direita)
    main_pane = ttk.PanedWindow(self.zone_tab_frame, orient="horizontal")
    main_pane.pack(expand=True, fill="both")
    
    # 3. Painel de controles (esquerda) - NOVO COMPONENTE
    left_panel_frame = ttk.Frame(
        main_pane, padding=5, relief="groove", borderwidth=2
    )
    main_pane.add(left_panel_frame, weight=1)
    
    # ✨ NOVO: Usar ZoneControlsWidget ao invés de criar 500+ linhas inline
    self.zone_controls = ZoneControlsWidget(
        left_panel_frame,
        event_bus=self.event_bus
    )
    self.zone_controls.pack(fill="both", expand=True)
    
    # 4. Painel de visualização (direita)
    self.viz_frame = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
    main_pane.add(self.viz_frame, weight=4)
    
    # ✨ NOVO: Usar VideoDisplayWidget ao invés de Canvas manual
    self.video_display = VideoDisplayWidget(
        self.viz_frame,
        event_bus=self.event_bus,
        width=800,
        height=600,
        bg="gray"
    )
    self.video_display.pack(fill="both", expand=True)
    
    # Manter referência ao canvas para compatibilidade com código de desenho existente
    # (pode ser removido após migração completa da lógica de desenho)
    self.roi_canvas = self.video_display.canvas
    
    # 5. Configurar posição inicial do divisor (mantido do código original)
    def _set_initial_sash():
        try:
            main_pane.sashpos(0, 420)
        except Exception:
            pass
    main_pane.after(10, _set_initial_sash)
    
    # 6. Manter comportamento de largura mínima (mantido do código original)
    def _on_pane_configure(event=None):
        try:
            current_pos = main_pane.sashpos(0)
            if current_pos < 380:
                main_pane.sashpos(0, 380)
        except Exception:
            pass
    main_pane.bind("<Configure>", _on_pane_configure)
    
    # 7. ✨ NOVO: Subscrever eventos dos componentes
    self._subscribe_zone_component_events()
    
    # 8. Bindings de mouse para desenho (mantidos - lógica não mudou)
    self._bind_canvas_drawing_events()


def _subscribe_zone_component_events(self):
    """
    NOVO: Subscribe to zone control component events.
    
    Este método centraliza todas as subscrições de eventos do ZoneControlsWidget,
    delegando para os métodos existentes do ApplicationGUI.
    """
    if not self.event_bus:
        return
    
    # Eventos de desenho
    self.event_bus.subscribe(
        "zone.auto_detect_clicked",
        lambda data: self._handle_auto_detect_event(data)
    )
    
    self.event_bus.subscribe(
        "zone.draw_main_polygon",
        lambda data: self._start_main_arena_drawing()
    )
    
    self.event_bus.subscribe(
        "zone.draw_roi",
        lambda data: self._start_roi_drawing()
    )
    
    self.event_bus.subscribe(
        "zone.toggle_view",
        lambda data: self._toggle_canvas_view()
    )
    
    # Eventos de template
    self.event_bus.subscribe(
        "zone.template_apply",
        lambda data: self._on_apply_roi_template_from_event(data)
    )
    
    self.event_bus.subscribe(
        "zone.template_save",
        lambda data: self._on_save_roi_template()
    )
    
    self.event_bus.subscribe(
        "zone.template_import",
        lambda data: self._on_import_and_apply_roi_template()
    )
    
    # Eventos de vídeo
    self.event_bus.subscribe(
        "zone.video_double_click",
        lambda data: self._on_video_tree_double_click_event(data)
    )
    
    self.event_bus.subscribe(
        "zone.video_frame_load",
        lambda data: self._load_selected_video_frame()
    )
    
    self.event_bus.subscribe(
        "zone.video_refresh",
        lambda data: self._populate_video_selector_tree()
    )
    
    self.event_bus.subscribe(
        "zone.video_search_changed",
        lambda data: self._filter_video_tree()
    )
    
    # Eventos de lista de zonas
    self.event_bus.subscribe(
        "zone.list_item_right_click",
        lambda data: self._on_zone_right_click_event(data)
    )
    
    self.event_bus.subscribe(
        "zone.list_item_double_click",
        lambda data: self._on_zone_double_click_event(data)
    )
    
    # Eventos de edição de arena
    self.event_bus.subscribe(
        "zone.arena_save",
        lambda data: self._on_save_arena()
    )
    
    self.event_bus.subscribe(
        "zone.arena_discard",
        lambda data: self._on_discard_arena()
    )
    
    # Eventos de configuração de ROI
    self.event_bus.subscribe(
        "zone.roi_rule_changed",
        lambda data: self._on_roi_rule_change(data)
    )
    
    self.event_bus.subscribe(
        "zone.roi_settings_apply",
        lambda data: self._on_apply_roi_settings()
    )


def _bind_canvas_drawing_events(self):
    """
    Bind canvas mouse events for drawing (mantido do código original).
    
    Esta lógica permanece inalterada, pois o desenho interativo ainda
    usa os mesmos event handlers.
    """
    self.roi_canvas.bind("<Button-1>", self._on_canvas_click)
    self.roi_canvas.bind("<Motion>", self._on_canvas_motion)
    self.roi_canvas.bind("<Double-Button-1>", self._on_canvas_double_click)


# Novos event handlers que adaptam eventos dos componentes

def _handle_auto_detect_event(self, data: dict):
    """Handle auto-detect event from ZoneControlsWidget."""
    stabilization_frames = data.get("stabilization_frames", 10)
    # Delegar para o método existente (pode precisar de adaptação)
    self._on_auto_detect_clicked()


def _on_apply_roi_template_from_event(self, data: dict):
    """Handle template apply event from ZoneControlsWidget."""
    template_name = data.get("template_name")
    if template_name:
        # Delegar para o método existente
        self._on_apply_roi_template()


def _on_video_tree_double_click_event(self, data: dict):
    """Handle video tree double-click event from ZoneControlsWidget."""
    # Criar evento mock compatível com o handler existente
    class MockEvent:
        pass
    
    # Delegar para o método existente
    self._on_video_tree_double_click(MockEvent())


def _on_zone_right_click_event(self, data: dict):
    """Handle zone right-click event from ZoneControlsWidget."""
    # Criar evento mock compatível com o handler existente
    class MockEvent:
        def __init__(self, x, y):
            self.x_root = x
            self.y_root = y
    
    event = MockEvent(data["x"], data["y"])
    self._on_zone_right_click(event)


def _on_zone_double_click_event(self, data: dict):
    """Handle zone double-click event from ZoneControlsWidget."""
    # Criar evento mock compatível com o handler existente
    class MockEvent:
        pass
    
    self._on_zone_double_click(MockEvent())


def _on_roi_rule_change(self, data: dict):
    """Handle ROI rule change event from ZoneControlsWidget."""
    # Criar evento mock compatível com o handler existente
    class MockEvent:
        pass
    
    self._on_roi_rule_change(MockEvent())


# Adaptações necessárias em métodos existentes

def _populate_video_selector_tree_ADAPTED(self):
    """
    ADAPTADO: Populate video selector tree using component API.
    
    Mudanças:
    - Usar self.zone_controls.video_selector_tree ao invés de self.video_selector_tree
    - Resto da lógica permanece igual
    """
    if not self.controller.project_manager.project_path:
        return
    
    # MUDANÇA: Usar widget do componente
    tree = self.zone_controls.video_selector_tree
    if not tree:
        return
    
    # Limpar árvore
    for item in tree.get_children():
        tree.delete(item)
    
    # ... resto da lógica existente permanece igual


def _refresh_roi_templates_ADAPTED(self):
    """
    ADAPTADO: Refresh ROI templates using component API.
    
    Mudanças:
    - Usar self.zone_controls.update_template_list() ao invés de
      atualizar self.roi_template_combobox diretamente
    """
    templates_dir = Path(self.controller.project_manager.project_path) / "templates"
    
    if not templates_dir.exists():
        template_names = []
    else:
        template_names = [
            f.stem for f in templates_dir.glob("*.json")
        ]
    
    # MUDANÇA: Usar API do componente
    self.zone_controls.update_template_list(template_names)


def redraw_zones_from_project_data_ADAPTED(self):
    """
    ADAPTADO: Redraw zones using VideoDisplayWidget API.
    
    Mudanças:
    - Usar self.video_display.canvas ao invés de self.roi_canvas
    - Usar self.video_display.video_to_canvas() para conversão de coordenadas
    """
    zones = self.controller.project_manager.get_zones()
    
    if not zones:
        return
    
    # MUDANÇA: Usar canvas do componente
    canvas = self.video_display.canvas
    
    # Limpar zonas existentes
    canvas.delete("zone")
    canvas.delete("roi")
    
    for zone_name, zone_data in zones.items():
        polygon = zone_data.get("polygon", [])
        
        if not polygon:
            continue
        
        # MUDANÇA: Usar método de conversão do componente
        canvas_points = []
        for x, y in polygon:
            cx, cy = self.video_display.video_to_canvas(x, y)
            canvas_points.extend([cx, cy])
        
        # Desenhar polígono
        color = zone_data.get("bgr_color", (0, 255, 0))
        rgb_color = f"#{color[2]:02x}{color[1]:02x}{color[0]:02x}"
        
        tag = "zone" if zone_data.get("type") == "arena" else "roi"
        
        canvas.create_polygon(
            canvas_points,
            outline=rgb_color,
            fill="",
            width=2,
            tags=tag
        )


# Compatibilidade retroativa: mapear atributos antigos para novos componentes

@property
def roi_canvas(self):
    """
    Propriedade de compatibilidade: mapeia roi_canvas para video_display.canvas.
    
    Permite que código legado continue funcionando durante migração gradual.
    Deve ser removido após migração completa.
    """
    if hasattr(self, 'video_display') and self.video_display:
        return self.video_display.canvas
    return None


@roi_canvas.setter
def roi_canvas(self, value):
    """Setter compatível (não faz nada, pois canvas é criado pelo componente)."""
    pass


@property
def zone_listbox(self):
    """
    Propriedade de compatibilidade: mapeia zone_listbox para zone_controls.zone_listbox.
    """
    if hasattr(self, 'zone_controls') and self.zone_controls:
        return self.zone_controls.zone_listbox
    return None


@property
def draw_roi_button(self):
    """
    Propriedade de compatibilidade: mapeia draw_roi_button para zone_controls.draw_roi_button.
    """
    if hasattr(self, 'zone_controls') and self.zone_controls:
        return self.zone_controls.draw_roi_button
    return None


# Exemplo de como atualizar métodos que controlam estado de widgets

def setup_zone_configuration_for_video_ADAPTED(self, video_path):
    """
    ADAPTADO: Setup zone configuration using component API.
    
    Mudanças:
    - Usar APIs públicas dos componentes ao invés de acessar widgets diretamente
    """
    # Carregar frame do vídeo no display
    self.video_display.load_frame(video_path, frame_number=0)
    
    # Habilitar botão de ROI
    self.zone_controls.set_draw_roi_enabled(True)
    
    # Mostrar opções de análise única (se necessário)
    # self.zone_controls.show_single_analysis_options()
    
    # ... resto da lógica


"""
RESUMO DAS MUDANÇAS:

1. ✅ Substituído código inline por ZoneControlsWidget (~500 linhas → ~50 linhas)
2. ✅ Substituído Canvas manual por VideoDisplayWidget (scaling automático)
3. ✅ Adicionadas subscrições de eventos centralizadas
4. ✅ Criados adapters para compatibilidade com código existente
5. ✅ Adicionadas propriedades de compatibilidade para migração gradual

BENEFÍCIOS:

- 📉 Redução de ~90% de código na criação da tab
- 🧪 Componentes testáveis isoladamente
- 🔄 Lógica reutilizável em outras tabs
- 📚 Código mais legível e manutenível
- 🎯 Separação clara entre UI e lógica de negócio

PRÓXIMOS PASSOS:

1. Implementar esta mudança incrementalmente
2. Testar cada função após migração
3. Remover propriedades de compatibilidade após migração completa
4. Migrar outras tabs seguindo o mesmo padrão
"""
