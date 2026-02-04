# Análise de Métodos para ProjectViewManager Component

## Resumo Executivo

Este documento detalha 34 métodos extraídos de `/src/zebtrack/ui/gui.py` para criação de um novo componente **ProjectViewManager**. O método `_build_status_token` mencionado na linha 1590 não foi encontrado - aquele local contém apenas dados de estrutura, não código de método.

**Nota Importante**: O método `_format_status_token` (linha 3585) é um método estático (`@staticmethod`), enquanto a maioria dos outros são métodos de instância.

---

## Métodos Extraídos (34 total)

### 1. update_tree_selection

**Linhas**: 170-176  
**Tipo**: Método de instância  
**Classe**: `_VideoHierarchyHelper` (não é ApplicationGUI)

```python
def update_tree_selection(self) -> None:
    """Update tree selection to show resolved video nodes."""
    if self.had_hierarchy_nodes and self.resolved_video_nodes:
        try:
            self.tree.selection_set(tuple(self.resolved_video_nodes))
        except Exception:
            pass
```

**Dependências**:

- `self.had_hierarchy_nodes` (atributo)
- `self.resolved_video_nodes` (atributo)
- `self.tree` (atributo ttk.Treeview)

**Complexidade**: Baixa - validação simples e seleção de nós

---

### 2. _update_window_title

**Linhas**: 539-549  
**Tipo**: Método de instância

```python
def _update_window_title(self, project_name: str | None = None):
    """
    Updates the window title with optional project name.

    Args:
        project_name: Name of the current project, or None for default title
    """
    if project_name:
        self.root.title(f"DRerio LogAI - {project_name}")
    else:
        self.root.title("DRerio LogAI")
```

**Dependências**:

- `self.root` (Tk widget)
- Parâmetro `project_name` (opcional)

**Complexidade**: Muito baixa - formatação de string

---

### 3. _navigate_to_processing_reports_tab

**Linhas**: 1274-1287  
**Tipo**: Método de instância

```python
def _navigate_to_processing_reports_tab(self) -> None:
    """Navigate to the Processing and Reports tab."""
    if not self.notebook:
        return

    # Find the index of the Processing and Reports tab
    tab_count = self.notebook.index("end")
    for i in range(tab_count):
        tab_text = self.notebook.tab(i, "text")
        if "Processamento e Relatórios" in tab_text:
            self.notebook.select(i)
            return

    log.warning("gui.navigate.processing_reports_tab_not_found")
```

**Dependências**:

- `self.notebook` (ttk.Notebook widget)
- `log` (structlog logger)

**Complexidade**: Baixa - iteração linear sobre abas

---

### 4. _request_overview_refresh

**Linhas**: 1303-1328  
**Tipo**: Método de instância

```python
def _request_overview_refresh(
    self,
    reason: str | None = None,
    *,
    append_summary: bool = False,
    immediate: bool = False,
) -> None:
    if reason is not None:
        self._pending_overview_status = reason
        self._overview_status_append = append_summary

    if self._overview_refresh_job is not None:
        try:
            self.root.after_cancel(self._overview_refresh_job)
        except Exception:
            pass
        self._overview_refresh_job = None

    if immediate:
        self._refresh_project_overview()
        return

    try:
        self._overview_refresh_job = self.root.after(150, self._refresh_project_overview)
    except Exception:
        self._refresh_project_overview()
```

**Dependências**:

- `self._pending_overview_status` (atributo)
- `self._overview_status_append` (atributo)
- `self._overview_refresh_job` (atributo - agendador)
- `self.root` (Tk widget)
- `self._refresh_project_overview()` (método local)

**Complexidade**: Média - debouncing com cancelamento de job

**Padrão**: Debouncer pattern com fallback para execução imediata

---

### 5. refresh_project_views

**Linhas**: 1330-1361  
**Tipo**: Método de instância

```python
def refresh_project_views(
    self,
    reason: str | None = None,
    *,
    append_summary: bool = False,
    immediate: bool = False,
) -> None:
    """Refresh overview, pipeline, and reports panels in a single call."""

    log.info(
        "gui.project_refresh.dispatched",
        reason=reason,
        append_summary=append_summary,
        immediate=immediate,
    )

    self._request_overview_refresh(
        reason=reason,
        append_summary=append_summary,
        immediate=immediate,
    )

    # Refresh new unified tab if present
    if getattr(self, "processing_reports_widget", None):
        self._refresh_processing_reports_tab()

    # Legacy: Refresh old tabs if they still exist
    if getattr(self, "pipeline_video_tree", None):
        self._refresh_pipeline_video_table()

    if getattr(self, "reports_tree", None):
        self.update_reports_tree()
```

**Dependências**:

- `log` (structlog logger)
- `self._request_overview_refresh()` (método local)
- `self.processing_reports_widget` (widget)
- `self._refresh_processing_reports_tab()` (método local)
- `self.pipeline_video_tree` (widget)
- `self._refresh_pipeline_video_table()` (método local)
- `self.reports_tree` (widget)
- `self.update_reports_tree()` (método local)

**Complexidade**: Média - orquestração de múltiplas atualizações

**Padrão**: Facade pattern - agrupa múltiplas operações de refresh

---

### 6. _refresh_project_overview

**Linhas**: 1363-1414  
**Tipo**: Método de instância

```python
def _refresh_project_overview(self) -> None:
    self._overview_refresh_job = None

    controller = getattr(self, "controller", None)
    if not controller or not controller.project_manager:
        log.debug("gui.refresh_overview.no_controller_or_pm")
        return

    pm = controller.project_manager
    all_videos = pm.get_all_videos() or []

    log.debug(
        "gui.refresh_overview.start",
        video_count=len(all_videos),
        has_project_path=bool(pm.project_path),
    )

    # Allow display even when there's no project file
    # This enables single video workflow results to be shown
    if not all_videos and not pm.project_path:
        # No videos and no project - nothing to show
        log.debug("gui.refresh_overview.no_videos_and_no_project")
        return

    counts: Counter = Counter(
        (str(video.get("status") or "pending")).strip().lower() for video in all_videos
    )
    total = sum(counts.values())

    log.debug(
        "gui.refresh_overview.updating",
        total=total,
        counts=dict(counts),
    )
    self._update_project_overview_summary(counts, total, all_videos)
    # Tree removed in favor of unified Processing and Reports tab
    if getattr(self, "project_overview_tree", None):
        self._update_project_overview_tree(pm, all_videos)
    self._refresh_zone_indicators(all_videos)

    if self._pending_overview_status is not None:
        summary_line = self._compose_overview_status_line(total, counts)
        if summary_line:
            if self._overview_status_append and self._pending_overview_status:
                message = f"{self._pending_overview_status} • {summary_line}"
            elif self._pending_overview_status:
                message = f"{self._pending_overview_status} — {summary_line}"
            else:
                message = summary_line
            self.set_status(message)
        self._pending_overview_status = None
        self._overview_status_append = False
```

**Dependências**:

- `self._overview_refresh_job` (atributo)
- `self.controller` (ApplicationController)
- `self.controller.project_manager` (ProjectManager)
- `log` (structlog logger)
- `self._update_project_overview_summary()` (método local)
- `self.project_overview_tree` (widget)
- `self._update_project_overview_tree()` (método local)
- `self._refresh_zone_indicators()` (método local)
- `self._compose_overview_status_line()` (método local)
- `self.set_status()` (método local)
- `self._pending_overview_status` (atributo)
- `self._overview_status_append` (atributo)
- `Counter` (collections)

**Complexidade**: Alta - lógica de orquestração com múltiplas chamadas

**Padrão**: Orchestrator pattern - coordena múltiplos passos de refresh

---

### 7. _update_project_overview_summary

**Linhas**: 1433-1466  
**Tipo**: Método de instância

```python
def _update_project_overview_summary(
    self,
    counts: Counter,
    total: int,
    videos: list[dict] | None,
) -> None:
    """Update project overview summary (delegates to widget)."""
    if not self.project_overview_widget:
        return

    videos = videos or []

    summary_values: dict[str, int] = {"total": total}
    for status_key in PROJECT_STATUS_META:
        summary_values[status_key] = counts.get(status_key, 0)

    arena_ready = sum(1 for video in videos if video.get("has_arena"))
    rois_ready = sum(1 for video in videos if video.get("has_rois"))
    trajectory_ready = sum(1 for video in videos if video.get("has_trajectory"))
    summary_ready = sum(
        1
        for video in videos
        if video.get("has_summary")
        or video.get("has_complete_data")
        or (video.get("has_arena") and video.get("has_rois") and video.get("has_trajectory"))
    )

    summary_values["arena"] = arena_ready
    summary_values["rois"] = rois_ready
    summary_values["trajectory"] = trajectory_ready
    summary_values["summary"] = summary_ready

    # Update widget with new counts
    self.project_overview_widget.update_status_counts(summary_values)
```

**Dependências**:

- `self.project_overview_widget` (ProjectOverviewWidget)
- `PROJECT_STATUS_META` (constante global)
- `Counter` (collections)
- Parâmetros: `counts`, `total`, `videos`

**Complexidade**: Média - computação de agregados

---

### 8. _update_project_overview_tree

**Linhas**: 1468-1488  
**Tipo**: Método de instância

```python
def _update_project_overview_tree(self, project_manager, all_videos: list[dict]) -> None:
    """Update the project overview tree (delegates to widget)."""
    if (
        not self.project_overview_widget
        or not self.project_overview_widget.project_overview_tree
    ):
        return

    self._overview_video_index = {}

    if not all_videos:
        self.project_overview_widget.clear_tree()
        return

    # Build hierarchy data structure
    hierarchy_data = self._prepare_overview_hierarchy_for_widget(all_videos)

    # Populate widget tree
    self.project_overview_widget.populate_tree_with_hierarchy(
        hierarchy_data, self._overview_video_index
    )
```

**Dependências**:

- `self.project_overview_widget` (ProjectOverviewWidget)
- `self._overview_video_index` (atributo - dict)
- `self._prepare_overview_hierarchy_for_widget()` (método local)
- Parâmetros: `project_manager`, `all_videos`

**Complexidade**: Média - delegação a métodos auxiliares

---

### 9. _format_status_label

**Linhas**: 1603-1605  
**Tipo**: Método de instância

```python
def _format_status_label(self, status_key: str) -> str:
    icon, label = self._get_status_meta(status_key)
    return f"{icon} {label}"
```

**Dependências**:

- `self._get_status_meta()` (método estático local)

**Complexidade**: Muito baixa - formatação simples

---

### 10. _format_status_summary

**Linhas**: 1607-1619  
**Tipo**: Método de instância

```python
def _format_status_summary(self, counts: Counter) -> str:
    parts: list[str] = []
    for key in PROJECT_STATUS_META:
        value = counts.get(key, 0)
        if value:
            icon, _ = PROJECT_STATUS_META[key]
            parts.append(f"{icon} {value}")

    others = sum(count for status, count in counts.items() if status not in PROJECT_STATUS_META)
    if others:
        parts.append(f"➕ {others}")

    return " | ".join(parts) if parts else "-"
```

**Dependências**:

- `Counter` (collections)
- `PROJECT_STATUS_META` (constante global)
- Parâmetro: `counts`

**Complexidade**: Baixa - iteração e formatação

---

### 11. _format_status_ratio

**Linhas**: 1622-1628  
**Tipo**: Método estático

```python
@staticmethod
def _format_status_ratio(symbol_key: str, completed: int, total: int) -> str:
    symbol = STATUS_SYMBOLS[symbol_key]
    safe_total = max(total, 0)
    clamped_completed = max(0, min(completed, safe_total)) if safe_total else 0
    if safe_total:
        return f"{symbol} {clamped_completed}/{safe_total}"
    return f"{symbol} 0/0"
```

**Dependências**:

- `STATUS_SYMBOLS` (constante global)

**Complexidade**: Baixa - validação e formatação numérica

---

### 12. _summarize_batch_data

**Linhas**: 1630-1650  
**Tipo**: Método de instância

```python
def _summarize_batch_data(self, videos: list[dict]) -> str:
    if not videos:
        return "-"

    total = len(videos)
    arena_count = sum(1 for video in videos if video.get("has_arena"))
    roi_count = sum(1 for video in videos if video.get("has_rois"))
    traj_count = sum(1 for video in videos if video.get("has_trajectory"))
    complete_count = sum(
        1
        for video in videos
        if video.get("has_complete_data")
        or (video.get("has_arena") and video.get("has_rois") and video.get("has_trajectory"))
    )

    return (
        f"{self._format_status_ratio('arena', arena_count, total)}  "
        f"{self._format_status_ratio('rois', roi_count, total)}  "
        f"{self._format_status_ratio('trajectory', traj_count, total)}  "
        f"{self._format_status_ratio('summary', complete_count, total)}"
    )
```

**Dependências**:

- `self._format_status_ratio()` (método estático local)
- Parâmetro: `videos`

**Complexidade**: Média - múltiplas agregações

---

### 13. _format_data_badges

**Linhas**: 1652-1666  
**Tipo**: Método de instância

```python
def _format_data_badges(self, video: dict) -> str:
    has_arena = bool(video.get("has_arena"))
    has_rois = bool(video.get("has_rois"))
    has_trajectory = bool(video.get("has_trajectory"))
    has_complete = bool(video.get("has_complete_data")) or (
        has_arena and has_rois and has_trajectory
    )

    markers = [
        self._format_status_token(has_arena, "arena"),
        self._format_status_token(has_rois, "rois"),
        self._format_status_token(has_trajectory, "trajectory"),
        self._format_status_token(has_complete, "summary"),
    ]
    return "  ".join(markers)
```

**Dependências**:

- `self._format_status_token()` (método estático local)
- Parâmetro: `video`

**Complexidade**: Baixa - mapeamento de status

---

### 14. _format_video_metadata

**Linhas**: 1668-1686  
**Tipo**: Método de instância

```python
def _format_video_metadata(self, metadata: dict) -> str:
    if not metadata:
        return ""

    parts: list[str] = []
    group = metadata.get("group")
    if group not in (None, ""):
        parts.append(f"G:{group}")

    day = metadata.get("day")
    if day not in (None, ""):
        day_display = metadata.get("day_label") or self._format_day_display(day)
        parts.append(f"D:{day_display or day}")

    subject = metadata.get("subject")
    if subject not in (None, ""):
        parts.append(f"S:{self._format_subject_label(subject)}")

    return " ".join(parts)
```

**Dependências**:

- `self._format_day_display()` (método local)
- `self._format_subject_label()` (método local)
- Parâmetro: `metadata`

**Complexidade**: Baixa - formatação condicional

---

### 15. _on_project_overview_tree_double_click

**Linhas**: 1688-1697  
**Tipo**: Método de instância

```python
def _on_project_overview_tree_double_click(self, event) -> None:
    """Handle double-click events on the overview tree (legacy handler)."""
    del event

    if not self.project_overview_tree:
        return

    item_id = self.project_overview_tree.focus()
    if item_id:
        self._on_project_overview_tree_double_click_impl(item_id)
```

**Dependências**:

- `self.project_overview_tree` (ttk.Treeview)
- `self._on_project_overview_tree_double_click_impl()` (método local)
- Parâmetro: `event`

**Complexidade**: Muito baixa - delegação

---

### 16. _on_project_overview_tree_double_click_impl

**Linhas**: 1699-1730  
**Tipo**: Método de instância

```python
def _on_project_overview_tree_double_click_impl(self, item_id: str) -> None:
    """Implementation of double-click logic (reusable)."""
    if not self.project_overview_tree:
        return

    tags = self.project_overview_tree.item(item_id, "tags") or ()
    if not tags:
        return

    video_path = tags[0]
    if not video_path or video_path.startswith("status_"):
        return

    if not os.path.exists(video_path):
        self.show_warning(
            "Arquivo não encontrado",
            f"O vídeo selecionado não foi localizado:\n{video_path}",
        )
        return

    success = self.canvas_manager.load_video_frame_to_canvas(video_path, frame_number=0)
    if success:
        self._maybe_offer_zone_reuse(video_path)
        self.canvas_manager.redraw_zones_from_project_data()
        message = f"Frame carregado: {os.path.basename(video_path)}"
        self.set_status(message)
        self._request_overview_refresh(reason=message, append_summary=True)
    else:
        self.show_error(
            "Erro ao Carregar",
            f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
        )
```

**Dependências**:

- `self.project_overview_tree` (ttk.Treeview)
- `self.canvas_manager` (CanvasManager)
- `self.show_warning()` (método local)
- `self.show_error()` (método local)
- `self._maybe_offer_zone_reuse()` (método local)
- `self._request_overview_refresh()` (método local)
- `self.set_status()` (método local)
- `os.path`

**Complexidade**: Alta - carregamento de vídeo e lógica de oferecimento de zona

---

### 17. _on_project_overview_right_click

**Linhas**: 1732-1742  
**Tipo**: Método de instância

```python
def _on_project_overview_right_click(self, event) -> None:
    """Handle right-click events on the overview tree (legacy handler)."""
    tree = self.project_overview_tree
    if not tree or not tree.winfo_exists():
        return

    item_id = tree.identify_row(event.y)
    if item_id:
        self.menu_manager.show_project_overview_context_menu(
            item_id, event.x_root, event.y_root
        )
```

**Dependências**:

- `self.project_overview_tree` (ttk.Treeview)
- `self.menu_manager` (MenuManager)
- Parâmetro: `event`

**Complexidade**: Baixa - delegação ao gerenciador de menu

---

### 18. _refresh_pipeline_video_table

**Linhas**: 2633-2800+  
**Tipo**: Método de instância

```python
def _refresh_pipeline_video_table(self, all_videos=None) -> None:
    """LEGACY: Replaced by _refresh_processing_reports_tab()."""
    if not self.pipeline_video_tree or not self.pipeline_tab_frame:
        return

    controller = getattr(self, "controller", None)
    pm = getattr(controller, "project_manager", None)

    if all_videos is None and pm is not None:
        all_videos = pm.get_all_videos() or []

    for item in self.pipeline_video_tree.get_children():
        self.pipeline_video_tree.delete(item)

    prepared_videos: list[dict] = []
    self.pipeline_video_vars = {}
    summary_total = 0

    for video in all_videos or []:
        path = video.get("path")
        if not path or not video.get("has_arena"):
            continue

        summary_exists = self._pipeline_summary_exists(video)

        prepared = dict(video)
        prepared["path"] = path
        prepared["metadata"] = video.get("metadata") or {}
        prepared["has_arena"] = bool(video.get("has_arena"))
        prepared["has_rois"] = bool(video.get("has_rois"))
        prepared["has_trajectory"] = bool(video.get("has_trajectory"))
        prepared["has_complete_data"] = bool(video.get("has_complete_data")) or (
            prepared["has_arena"] and prepared["has_rois"] and prepared["has_trajectory"]
        )
        prepared["has_summary"] = bool(summary_exists)
        prepared["filename"] = os.path.basename(path)

        prepared_videos.append(prepared)

        self.pipeline_video_vars[path] = {
            "info": video,
            "summary": summary_exists,
        }
        if summary_exists:
            summary_total += 1

    hierarchy = self._build_video_hierarchy_data(prepared_videos, "")

    def _count(entries: list[dict], key: str) -> int:
        return sum(1 for entry in entries if entry.get(key))

    def _summary_count(entries: list[dict]) -> int:
        return sum(
            1 for entry in entries if entry.get("has_summary") or entry.get("has_complete_data")
        )

    for group_id, group_data in sorted(
        hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
    ):
        days_dict = group_data.get("days") or {}
        group_entries = [entry for videos in days_dict.values() for entry in videos or []]
        if not group_entries:
            continue

        total_group = len(group_entries)
        group_node = self.pipeline_video_tree.insert(
            "",
            "end",
            text=f"🏷️ {group_data['display']}",
            values=(
                self._format_status_ratio(
                    "rois", _count(group_entries, "has_rois"), total_group
                ),
                self._format_status_ratio(
                    "trajectory",
                    _count(group_entries, "has_trajectory"),
                    total_group,
                ),
                self._format_status_ratio(
                    "summary", _summary_count(group_entries), total_group
                ),
                f"{total_group} vídeos",
            ),
            open=True,
        )

        for day_id, entries in sorted(
            days_dict.items(), key=lambda item: self._video_sort_key(item[0])
        ):
            # ... (continua com inserção de nós do dia)
```

**Dependências**:

- `self.pipeline_video_tree` (ttk.Treeview)
- `self.pipeline_tab_frame` (Frame)
- `self.controller` (ApplicationController)
- `self.pipeline_video_vars` (dict)
- `self._pipeline_summary_exists()` (método local)
- `self._build_video_hierarchy_data()` (método local)
- `self._format_status_ratio()` (método estático local)
- `self._video_sort_key()` (método local)

**Complexidade**: Muito alta - construção completa de árvore hierárquica

**Padrão**: LEGACY - substituído por `_refresh_processing_reports_tab()`

---

### 19. _resolve_processing_reports_video_paths

**Linhas**: 2856-2875  
**Tipo**: Método de instância

```python
def _resolve_processing_reports_video_paths(self, selection: Iterable[str] | None) -> list[str]:
    """Translate unified tab selections into concrete video paths."""
    if not selection:
        return []

    widget = getattr(self, "processing_reports_widget", None)
    tree = getattr(widget, "tree", None)
    if not tree:
        return []

    metadata_store = getattr(self, "_processing_reports_tree_metadata", {})
    context = _VideoPathResolverContext(tree, metadata_store)

    for item_id in selection:
        if not item_id or not tree.exists(item_id):
            continue
        context.process_item(item_id)

    context.update_tree_selection()
    return context.final_paths
```

**Dependências**:

- `self.processing_reports_widget` (ProcessingReportsWidget)
- `self._processing_reports_tree_metadata` (dict)
- `_VideoPathResolverContext` (classe local)
- Parâmetro: `selection`

**Complexidade**: Média - resolução de contexto

---

### 20. _update_pipeline_buttons_state

**Linhas**: 2894-2911  
**Tipo**: Método de instância

```python
def _update_pipeline_buttons_state(self, selections=None) -> None:
    if not self.pipeline_action_buttons:
        return
    if selections is None:
        selections = self._get_selected_pipeline_video_paths()

    has_selection = bool(selections)
    for button in self.pipeline_action_buttons.values():
        button.config(state="normal" if has_selection else "disabled")

    if has_selection:
        all_have_trajectory = all(
            bool(self.pipeline_video_vars.get(path, {}).get("info", {}).get("has_trajectory"))
            for path in selections
        )
        self.pipeline_action_buttons["summaries"].config(
            state="normal" if all_have_trajectory else "disabled"
        )
```

**Dependências**:

- `self.pipeline_action_buttons` (dict de buttons)
- `self.pipeline_video_vars` (dict)
- `self._get_selected_pipeline_video_paths()` (método local)
- Parâmetro: `selections`

**Complexidade**: Média - validação de estado

---

### 21. _populate_video_selector_tree

**Linhas**: 3589-3718  
**Tipo**: Método de instância

```python
def _populate_video_selector_tree(self, filter_text: str | None = None):
    """Popula a árvore hierárquica do seletor de vídeos."""

    if not self.video_selector_tree:
        return

    # Determine filter text priority: argument > entry value > stored filter
    if filter_text is None:
        if self.video_search_var is not None:
            filter_text = self.video_search_var.get()
        elif self._video_selector_filter:
            filter_text = self._video_selector_filter
        else:
            filter_text = ""

    search_text = (filter_text or "").strip().lower()
    self._video_selector_filter = search_text

    for item in self.video_selector_tree.get_children():
        self.video_selector_tree.delete(item)

    # Configure readiness color tags
    self.video_selector_tree.tag_configure("ready_full", foreground="#166534")
    self.video_selector_tree.tag_configure("ready_partial", foreground="#b45309")
    self.video_selector_tree.tag_configure("ready_missing", foreground="#b91c1c")
    self.video_selector_tree.tag_configure("ready_optional", foreground="#0369a1")

    controller = getattr(self, "controller", None)
    if not controller or not controller.project_manager:
        self._update_zone_summary_cards([])
        return

    pm = controller.project_manager
    if not pm.project_path:
        self._update_zone_summary_cards([])
        return

    all_videos = pm.get_all_videos()
    self._update_zone_summary_cards(all_videos)

    if not all_videos:
        return

    hierarchy = self._build_video_hierarchy_data(all_videos, search_text)
    readiness_tags = self._pending_readiness_snapshot or {}

    displayed_videos = 0

    def format_status(has_parquet: bool, symbol_key: str) -> str:
        symbol = STATUS_SYMBOLS[symbol_key]
        return f"{symbol} ✓" if has_parquet else f"{symbol} ✗"

    for group_id, group_data in sorted(
        hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
    ):
        days_dict = group_data["days"]
        total_group_videos = sum(len(videos) for videos in days_dict.values())
        if total_group_videos == 0:
            continue

        group_node = self.video_selector_tree.insert(
            "",
            "end",
            text=f"🏷️ {group_data['display']} ({group_id})",
            values=("", f"{total_group_videos} vídeos"),
            open=True,
        )

        for day_id, videos in sorted(
            days_dict.items(), key=lambda item: self._video_sort_key(item[0])
        ):
            if not videos:
                continue

            sample_metadata = videos[0].get("metadata") if videos else None
            day_title = self._build_day_title(day_id, sample_metadata)
            day_node = self.video_selector_tree.insert(
                group_node,
                "end",
                text=f"📅 {day_title}",
                values=("", f"{len(videos)} vídeos"),
                open=False,
            )

            for video_entry in sorted(
                videos,
                key=lambda entry: self._video_sort_key(entry.get("subject")),
            ):
                video_path = video_entry.get("path") or ""
                if not video_path:
                    continue

                subject_label = self._format_subject_label(video_entry.get("subject"))

                status_tokens = " ".join(
                    (
                        format_status(video_entry["has_arena"], "arena"),
                        format_status(video_entry["has_rois"], "rois"),
                        format_status(video_entry["has_trajectory"], "trajectory"),
                    )
                )

                extra_tags = readiness_tags.get(video_path, ())
                if extra_tags:
                    tag_tuple = (video_path, *extra_tags)
                else:
                    tag_tuple = (video_path,)

                self.video_selector_tree.insert(
                    day_node,
                    "end",
                    text=f"🐟 Sujeito {subject_label}",
                    values=(status_tokens, video_entry["filename"]),
                    tags=tag_tuple,
                )
                displayed_videos += 1

    zone_controls = getattr(self, "zone_controls", None)
    if zone_controls:
        zone_controls.apply_video_tree_expand_state()

    log.info(
        "gui.video_selector.populated",
        filter=self._video_selector_filter,
        groups=len(hierarchy),
        total_videos=len(all_videos),
        displayed=displayed_videos,
    )

    self._request_overview_refresh()
```

**Dependências**:

- `self.video_selector_tree` (ttk.Treeview)
- `self.video_search_var` (StringVar)
- `self._video_selector_filter` (atributo)
- `self.controller` (ApplicationController)
- `self._update_zone_summary_cards()` (método local)
- `self._build_video_hierarchy_data()` (método local)
- `self._pending_readiness_snapshot` (atributo)
- `STATUS_SYMBOLS` (constante global)
- `self._video_sort_key()` (método local)
- `self._build_day_title()` (método local)
- `self._format_subject_label()` (método local)
- `self.zone_controls` (widget)
- `log` (structlog logger)
- `self._request_overview_refresh()` (método local)
- Parâmetro: `filter_text`

**Complexidade**: Muito alta - construção completa de árvore com filtros

---

### 22. _format_status_token

**Linhas**: 3585-3587  
**Tipo**: Método estático

```python
@staticmethod
def _format_status_token(has_parquet: bool, symbol_key: str) -> str:
    symbol = STATUS_SYMBOLS[symbol_key]
    return f"{symbol} ✓" if has_parquet else f"{symbol} ✗"
```

**Dependências**:

- `STATUS_SYMBOLS` (constante global)

**Complexidade**: Muito baixa - formatação condicional

---

### 23. _refresh_video_selector_tree

**Linhas**: 3720-3740  
**Tipo**: Método de instância

```python
def _refresh_video_selector_tree(self) -> None:
    """Repopula a árvore mantendo seleção e filtros atuais sempre que possível."""

    if not self.video_selector_tree:
        return

    selected_tag = None
    selection = self.video_selector_tree.selection()
    if selection:
        try:
            tags = self.video_selector_tree.item(selection[0], "tags")
            if tags:
                selected_tag = tags[0]
        except Exception:
            selected_tag = None

    current_filter = getattr(self, "_video_selector_filter", "")
    self._populate_video_selector_tree(current_filter)

    if selected_tag:
        self._reselect_video_tree_item(selected_tag)
```

**Dependências**:

- `self.video_selector_tree` (ttk.Treeview)
- `self._video_selector_filter` (atributo)
- `self._populate_video_selector_tree()` (método local)
- `self._reselect_video_tree_item()` (método local)

**Complexidade**: Média - preservação de seleção durante refresh

---

### 24. _on_processing_reports_item_double_click

**Linhas**: 4011-4054  
**Tipo**: Método de instância

```python
def _on_processing_reports_item_double_click(self, event=None) -> None:
    """Handle double-click on items in the Processing Reports tree."""
    if not self.processing_reports_widget or not self.processing_reports_widget.tree:
        return

    tree = self.processing_reports_widget.tree

    # Get item at click position
    item_id = None
    if event is not None:
        item_id = tree.identify_row(event.y)
    if not item_id:
        selection = tree.selection()
        if selection:
            item_id = selection[0]
    if not item_id:
        return

    metadata = self._processing_reports_tree_metadata.get(item_id)
    if not metadata:
        return

    node_type = metadata.get("type")

    # Handle file nodes (docx/xlsx) - open them
    if node_type == "file":
        self._handle_report_file_node(metadata)
        return

    # Handle video nodes - open results folder
    if node_type == "video":
        results_dir = metadata.get("results_dir")
        if results_dir and os.path.exists(results_dir):
            log.info("gui.open_results_folder", path=results_dir)
            try:
                if os.name == "nt":  # Windows
                    os.startfile(results_dir)
                elif os.name == "posix":  # macOS, Linux
                    import subprocess

                    subprocess.Popen(["xdg-open", results_dir])
            except Exception as e:
                log.error("gui.open_results_folder.failed", error=str(e))
                self.show_error("Erro", f"Não foi possível abrir a pasta: {e}")
```

**Dependências**:

- `self.processing_reports_widget` (ProcessingReportsWidget)
- `self._processing_reports_tree_metadata` (dict)
- `self._handle_report_file_node()` (método local)
- `log` (structlog logger)
- `os.path`, `os.name`, `os.startfile`, `subprocess`
- `self.show_error()` (método local)
- Parâmetro: `event`

**Complexidade**: Média - manipulação de arquivo e pasta

---

### 25. _on_processing_reports_generate_partial

**Linhas**: 4056-4085  
**Tipo**: Método de instância

```python
def _on_processing_reports_generate_partial(self) -> None:
    """Handle partial report generation from the unified tab."""
    if not self.processing_reports_widget:
        return

    selection = self.processing_reports_widget.get_selection()
    if not selection:
        return

    selected_videos = []
    all_videos = self.controller.project_manager.get_all_videos()
    metadata_store = getattr(self, "_processing_reports_tree_metadata", {})

    for item_id in selection:
        metadata = metadata_store.get(item_id)
        if not metadata or metadata.get("type") != "video":
            continue
        video_path = metadata.get("video_path")
        if not video_path:
            continue
        for video_data in all_videos:
            if video_data["path"] == video_path:
                selected_videos.append(video_data)
                break

    if selected_videos:
        self.event_dispatcher.publish_event(
            Events.REPORT_GENERATE,
            {"videos": selected_videos, "report_type": "partial"},
        )
```

**Dependências**:

- `self.processing_reports_widget` (ProcessingReportsWidget)
- `self.controller` (ApplicationController)
- `self.controller.project_manager` (ProjectManager)
- `self._processing_reports_tree_metadata` (dict)
- `self.event_dispatcher` (EventDispatcher)
- `Events` (enum)

**Complexidade**: Média - resolução de seleção em evento

---

### 26. _refresh_processing_reports_tab

**Linhas**: 4087-4240+  
**Tipo**: Método de instância

```python
def _refresh_processing_reports_tab(self) -> None:
    """
    Refresh the unified Processing and Reports tab.

    Consolidates logic from _refresh_pipeline_video_table() and update_reports_tree().
    """
    if not self.processing_reports_widget:
        return

    widget = self.processing_reports_widget

    controller = getattr(self, "controller", None)
    if not controller or not controller.project_manager:
        log.debug("gui.refresh_processing_reports.no_controller_or_pm")
        return

    pm = controller.project_manager
    all_videos = pm.get_all_videos() or []

    log.debug(
        "gui.refresh_processing_reports.start",
        video_count=len(all_videos),
        has_project_path=bool(pm.project_path),
    )

    # Clear tree and metadata
    widget.clear_tree()
    self._processing_reports_tree_metadata.clear()

    if not all_videos:
        log.debug("gui.refresh_processing_reports.no_videos")
        return

    # Update status cards
    from collections import Counter

    counts: Counter = Counter(
        (str(video.get("status") or "pending")).strip().lower() for video in all_videos
    )
    total = sum(counts.values())

    status_counts = {
        "total": total,
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "processed": counts.get("processed", 0),
        "complete": counts.get("complete", 0),
        "failed": counts.get("failed", 0),
    }

    widget.update_status_counts(status_counts)

    # Build hierarchy (Group > Day > Subject)
    hierarchy = self._build_report_hierarchy(all_videos, pm)

    # Populate tree
    for group_id, group_data in sorted(
        hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
    ):
        videos_by_day = group_data["days"]
        total_videos = sum(len(items) for items in videos_by_day.values())
        if total_videos == 0:
            continue

        total_arena = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_arena"]
        )
        total_rois = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_rois"]
        )
        total_trajectory = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_trajectory"]
        )
        total_summary = sum(
            1
            for items in videos_by_day.values()
            for entry in items
            if entry["has_complete_data"] or entry.get("has_summary")
        )

        # Determine color tag for group based on completion
        group_tag = self._determine_status_tag(total_summary, total_videos)

        group_node_id = f"group_{group_id}"
        widget.add_tree_item(
            item_id=group_node_id,
            text=f"🏷️ {group_data['display']}",
            values=(
                self._format_status_ratio("arena", total_arena, total_videos),
                self._format_status_ratio("rois", total_rois, total_videos),
                self._format_status_ratio("trajectory", total_trajectory, total_videos),
                self._format_status_ratio("summary", total_summary, total_videos),
                f"{total_videos} vídeos",
            ),
            tags=(group_tag,),
        )
        widget.expand_tree_item(group_node_id)

        self._processing_reports_tree_metadata[group_node_id] = {
            "type": "group",
            # ... (continua com mais dados)
```

**Dependências**:

- `self.processing_reports_widget` (ProcessingReportsWidget)
- `self.controller` (ApplicationController)
- `self.controller.project_manager` (ProjectManager)
- `self._processing_reports_tree_metadata` (dict)
- `log` (structlog logger)
- `Counter` (collections)
- `self._build_report_hierarchy()` (método local)
- `self._determine_status_tag()` (método local)
- `self._format_status_ratio()` (método estático local)
- `self._append_processing_reports_artifacts()` (método local)

**Complexidade**: Muito alta - construção completa de árvore unificada

**Padrão**: Consolidação de duas operações legadas em uma

---

### 27. _append_processing_reports_artifacts

**Linhas**: 4313-4377  
**Tipo**: Método de instância

```python
def _append_processing_reports_artifacts(
    self, widget, parent_id: str, entry: dict, video_path: str
) -> None:
    """
    Append report artifacts (docx, xlsx) as children of a video node.

    Args:
        widget: The ProcessingReportsWidget instance
        parent_id: Parent tree node ID
        entry: Video entry dictionary
        video_path: Path to the video file
    """
    results_dir = entry.get("results_dir") or ""
    parquet_files = entry.get("parquet_files") or {}
    experiment_id = Path(video_path).stem if video_path else None

    def _resolve_artifact(candidate: str | None, suffix: str) -> str | None:
        if candidate and os.path.exists(candidate):
            return candidate
        if results_dir and experiment_id:
            guess_path = Path(results_dir) / f"{experiment_id}_{suffix}"
            if guess_path.exists():
                return str(guess_path)
        return None

    docx_path = _resolve_artifact(
        parquet_files.get("report_docx"),
        "report.docx",
    )
    excel_path = _resolve_artifact(
        parquet_files.get("summary_excel"),
        "summary.xlsx",
    )

    artifacts: list[tuple[str, str, str]] = []
    if docx_path:
        artifacts.append(("file", docx_path, "📝 Word: " + Path(docx_path).name))
    if excel_path:
        artifacts.append(("file", excel_path, "📊 Excel: " + Path(excel_path).name))

    if not artifacts:
        return

    tree = widget.tree

    for _kind, artifact_path, label in artifacts:
        child_id = self._build_processing_report_artifact_id(parent_id, artifact_path)
        if tree and tree.exists(child_id):
            continue

        widget.add_tree_item(
            item_id=child_id,
            text=label,
            parent=parent_id,
            values=("", "", "", "", "Abrir"),
            tags=("report-file",),
        )
        self._processing_reports_tree_metadata[child_id] = {
            "type": "file",
            "path": artifact_path,
            "parent_video": video_path,
        }

    # Expand video node to show report files
    widget.expand_tree_item(parent_id)
```

**Dependências**:

- `Path` (pathlib)
- `self._build_processing_report_artifact_id()` (método local)
- `self._processing_reports_tree_metadata` (dict)
- Parâmetros: `widget`, `parent_id`, `entry`, `video_path`

**Complexidade**: Média - resolução de artefatos e inserção

---

### 28. update_reports_tree

**Linhas**: 4379-4427  
**Tipo**: Método de instância

```python
def update_reports_tree(self):
    """
    LEGACY: Replaced by _refresh_processing_reports_tab().

    This method is kept for backward compatibility.
    """
    if not hasattr(self, "reports_tree") or self.reports_tree is None:
        log.debug("gui.update_reports.legacy_tree_missing")
        return

    # Clear existing tree
    for item in self.reports_tree.get_children():
        self.reports_tree.delete(item)

    # Reset metadata store
    if not hasattr(self, "_report_tree_metadata"):
        self._report_tree_metadata = {}
    else:
        self._report_tree_metadata.clear()

    controller = getattr(self, "controller", None)
    if not controller or not controller.project_manager:
        log.debug("gui.update_reports.no_controller_or_pm")
        return

    pm = controller.project_manager
    all_videos = pm.get_all_videos()

    log.debug(
        "gui.update_reports.start",
        video_count=len(all_videos) if all_videos else 0,
        has_project_path=bool(pm.project_path),
    )

    if not all_videos:
        log.debug("gui.update_reports.no_videos")
        return

    hierarchy = self._build_report_hierarchy(all_videos, pm)
    self._populate_reports_tree_from_hierarchy(hierarchy, pm)

    log.info(
        "gui.reports_tree.updated",
        groups=len(hierarchy),
        total_videos=len(all_videos),
    )

    # Keep selector synced
    self._populate_video_selector_tree()
```

**Dependências**:

- `self.reports_tree` (ttk.Treeview)
- `self._report_tree_metadata` (dict)
- `self.controller` (ApplicationController)
- `log` (structlog logger)
- `self._build_report_hierarchy()` (método local)
- `self._populate_reports_tree_from_hierarchy()` (método local)
- `self._populate_video_selector_tree()` (método local)

**Complexidade**: Média - orquestração legada

**Padrão**: LEGACY - mantido para compatibilidade com versões antigas

---

### 29. _populate_reports_tree_from_hierarchy

**Linhas**: 4503-4612  
**Tipo**: Método de instância

```python
def _populate_reports_tree_from_hierarchy(self, hierarchy: dict, pm) -> None:
    """Insert nodes into the reports tree from a precomputed hierarchy."""
    for group_id, group_data in sorted(
        hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
    ):
        videos_by_day = group_data["days"]
        total_videos = sum(len(items) for items in videos_by_day.values())
        if total_videos == 0:
            continue
        total_arena = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_arena"]
        )
        total_rois = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_rois"]
        )
        total_trajectory = sum(
            1 for items in videos_by_day.values() for entry in items if entry["has_trajectory"]
        )
        total_complete = sum(
            1
            for items in videos_by_day.values()
            for entry in items
            if entry["has_complete_data"] or entry.get("has_summary")
        )

        group_node = self.reports_tree.insert(
            "",
            "end",
            text=f"🏷️ {group_data['display']}",
            values=(
                self._format_status_ratio("arena", total_arena, total_videos),
                self._format_status_ratio("rois", total_rois, total_videos),
                self._format_status_ratio("trajectory", total_trajectory, total_videos),
                self._format_status_ratio("summary", total_complete, total_videos),
                f"{total_videos} vídeos",
            ),
            open=True,
        )

        self._report_tree_metadata[group_node] = {"type": "group", "identifier": group_id}

        for day_id, entries in sorted(
            videos_by_day.items(), key=lambda item: self._sort_key_for_reports(item[0])
        ):
            if not entries:
                continue
            day_arena = sum(1 for entry in entries if entry["has_arena"])
            day_rois = sum(1 for entry in entries if entry["has_rois"])
            day_trajectory = sum(1 for entry in entries if entry["has_trajectory"])
            day_complete = sum(
                1 for entry in entries if entry["has_complete_data"] or entry.get("has_summary")
            )
            sample_metadata = entries[0].get("metadata") if entries else None
            day_title = self._build_day_title(day_id, sample_metadata)

            day_node = self.reports_tree.insert(
                group_node,
                "end",
                text=f"📅 {day_title}",
                values=(
                    self._format_status_ratio("arena", day_arena, len(entries)),
                    self._format_status_ratio("rois", day_rois, len(entries)),
                    self._format_status_ratio("trajectory", day_trajectory, len(entries)),
                    self._format_status_ratio("summary", day_complete, len(entries)),
                    f"{len(entries)} vídeos",
                ),
                open=False,
            )

            self._report_tree_metadata[day_node] = {
                "type": "day",
                "identifier": day_id,
                "group_id": group_id,
            }

            for entry in sorted(
                entries, key=lambda item: self._sort_key_for_reports(item.get("subject"))
            ):
                video_path = entry.get("path")
                if not video_path:
                    continue

                subject_label = self._format_subject_for_reports(entry.get("subject"))

                video_node = self.reports_tree.insert(
                    day_node,
                    "end",
                    text=(f"🐟 Sujeito {subject_label}  ({entry['filename']})"),
                    values=(
                        self._format_status_token(entry["has_arena"], "arena"),
                        self._format_status_token(entry["has_rois"], "rois"),
                        self._format_status_token(entry["has_trajectory"], "trajectory"),
                        self._format_status_token(
                            entry.get("has_summary") or entry.get("has_complete_data"),
                            "summary",
                        ),
                        entry["status"],
                    ),
                    tags=("video-node",),
                )

                self._report_tree_metadata[video_node] = {
                    "type": "video",
                    "video_path": video_path,
                    "results_dir": entry.get("results_dir") or "",
                    "parquet_files": entry.get("parquet_files") or {},
                    "metadata": entry.get("metadata") or {},
                }

                self._append_report_artifacts(video_node, entry)
```

**Dependências**:

- `self.reports_tree` (ttk.Treeview)
- `self._report_tree_metadata` (dict)
- `self._format_status_ratio()` (método estático local)
- `self._sort_key_for_reports()` (método local)
- `self._build_day_title()` (método local)
- `self._format_subject_for_reports()` (método local)
- `self._format_status_token()` (método estático local)
- `self._append_report_artifacts()` (método local)
- Parâmetros: `hierarchy`, `pm`

**Complexidade**: Muito alta - construção completa de árvore de três níveis

---

### 30. _append_report_artifacts

**Linhas**: 4614-4668  
**Tipo**: Método de instância

```python
def _append_report_artifacts(self, parent_id: str, entry: dict) -> None:
    tree = getattr(self, "reports_tree", None)
    if not tree:
        return

    video_path = entry.get("path")
    if not video_path:
        return

    results_dir = entry.get("results_dir") or ""
    parquet_files = entry.get("parquet_files") or {}
    experiment_id = Path(video_path).stem if video_path else None

    def _resolve_artifact(candidate: str | None, suffix: str) -> str | None:
        if candidate and os.path.exists(candidate):
            return candidate
        if results_dir and experiment_id:
            guess_path = Path(results_dir) / f"{experiment_id}_{suffix}"
            if guess_path.exists():
                return str(guess_path)
        return None

    docx_path = _resolve_artifact(
        parquet_files.get("report_docx"),
        "report.docx",
    )
    excel_path = _resolve_artifact(
        parquet_files.get("summary_excel"),
        "summary.xlsx",
    )

    artifacts: list[tuple[str, str, str]] = []
    if docx_path:
        artifacts.append(("file", docx_path, "📝 Word: " + Path(docx_path).name))
    if excel_path:
        artifacts.append(("file", excel_path, "📊 Excel: " + Path(excel_path).name))

    if not artifacts:
        return

    for _kind, artifact_path, label in artifacts:
        child_id = tree.insert(
            parent_id,
            "end",
            text=label,
            values=("", "", "", "", "Abrir"),
            tags=("report-file",),
        )
        self._report_tree_metadata[child_id] = {
            "type": "file",
            "path": artifact_path,
            "parent_video": video_path,
        }

    tree.item(parent_id, open=True)
```

**Dependências**:

- `self.reports_tree` (ttk.Treeview)
- `self._report_tree_metadata` (dict)
- `Path` (pathlib)
- Parâmetros: `parent_id`, `entry`

**Complexidade**: Média - resolução de artefatos

---

### 31. _on_report_item_select

**Linhas**: 4670-4684  
**Tipo**: Método de instância

```python
def _on_report_item_select(self, event=None):
    """Enables or disables the partial report button based on selection."""
    selection = self.reports_tree.selection()
    has_video = False
    metadata_store = getattr(self, "_report_tree_metadata", {})
    for item_id in selection:
        metadata = metadata_store.get(item_id)
        if metadata and metadata.get("type") == "video":
            has_video = True
            break

    if has_video:
        self.generate_partial_report_btn.config(state="normal")
    else:
        self.generate_partial_report_btn.config(state="disabled")
```

**Dependências**:

- `self.reports_tree` (ttk.Treeview)
- `self._report_tree_metadata` (dict)
- `self.generate_partial_report_btn` (Button)
- Parâmetro: `event`

**Complexidade**: Baixa - validação e ativação de botão

---

### 32. _on_report_item_double_click

**Linhas**: 4686-4716  
**Tipo**: Método de instância

```python
def _on_report_item_double_click(self, event=None):
    """Open the results folder for the selected video when reports exist."""
    tree = getattr(self, "reports_tree", None)
    if not tree:
        return

    item_id = None
    if event is not None:
        item_id = tree.identify_row(event.y)
    if not item_id:
        selection = tree.selection()
        if selection:
            item_id = selection[0]
    if not item_id:
        return

    metadata_store = getattr(self, "_report_tree_metadata", {})
    metadata = metadata_store.get(item_id)
    if not metadata:
        return

    node_type = metadata.get("type")

    if node_type == "file":
        self._handle_report_file_node(metadata)
        return

    if node_type != "video":
        return

    self._handle_report_video_node(metadata)
```

**Dependências**:

- `self.reports_tree` (ttk.Treeview)
- `self._report_tree_metadata` (dict)
- `self._handle_report_file_node()` (método local)
- `self._handle_report_video_node()` (método local)
- Parâmetro: `event`

**Complexidade**: Média - delegação por tipo de nó

---

### 33. _update_delete_template_button_state

**Linhas**: 5853-5862  
**Tipo**: Método de instância

```python
def _update_delete_template_button_state(self) -> None:
    """Update the delete template button state based on selection."""
    if not self.delete_template_btn:
        return

    current_value = self.roi_template_var.get().strip()
    if current_value and self._get_selected_roi_template():
        self.delete_template_btn.config(state="normal")
    else:
        self.delete_template_btn.config(state="disabled")
```

**Dependências**:

- `self.delete_template_btn` (Button)
- `self.roi_template_var` (StringVar)
- `self._get_selected_roi_template()` (método local)

**Complexidade**: Baixa - validação de estado

---

### 34. _refresh_openvino_summary

**Linhas**: 7095-7101  
**Tipo**: Método de instância

```python
def _refresh_openvino_summary(self):
    state_text = "Ativado" if self._openvino_enabled else "Desativado"
    status_text = self._openvino_status_message.strip()
    if status_text:
        self._openvino_display_var.set(f"OpenVINO: {state_text} — {status_text}")
    else:
        self._openvino_display_var.set(f"OpenVINO: {state_text}")
```

**Dependências**:

- `self._openvino_enabled` (atributo bool)
- `self._openvino_status_message` (atributo str)
- `self._openvino_display_var` (StringVar)

**Complexidade**: Muito baixa - formatação de string condicional

---

## Resumo de Categorias

### Por Complexidade

- **Muito Baixa** (10): `_update_window_title`, `_format_status_label`, `_format_status_ratio`, `_format_status_token`, `_on_report_item_select`, `_update_delete_template_button_state`, `_refresh_openvino_summary`
- **Baixa** (8): `_navigate_to_processing_reports_tab`, `_format_status_summary`, `_format_data_badges`, `_format_video_metadata`, `_on_project_overview_tree_double_click`, `_on_project_overview_right_click`, `_refresh_video_selector_tree`, `_on_processing_reports_item_double_click`
- **Média** (9): `_request_overview_refresh`, `_update_project_overview_summary`, `_update_project_overview_tree`, `_summarize_batch_data`, `_resolve_processing_reports_video_paths`, `_update_pipeline_buttons_state`, `_on_processing_reports_generate_partial`, `_append_processing_reports_artifacts`, `update_reports_tree`, `_append_report_artifacts`, `_on_report_item_double_click`
- **Alta** (2): `_refresh_project_overview`, `_on_project_overview_tree_double_click_impl`
- **Muito Alta** (4): `refresh_project_views`, `_refresh_pipeline_video_table`, `_populate_video_selector_tree`, `_refresh_processing_reports_tab`, `_populate_reports_tree_from_hierarchy`

### Por Padrão

- **Debouncer**: `_request_overview_refresh`
- **Facade**: `refresh_project_views`, `update_reports_tree`
- **Orchestrator**: `_refresh_project_overview`, `_refresh_processing_reports_tab`
- **Delegator**: `_update_project_overview_tree`, `_on_project_overview_tree_double_click`
- **Resolver**: `_resolve_processing_reports_video_paths`
- **Formatter**: `_format_status_label`, `_format_status_summary`, `_format_status_ratio`, `_format_status_token`, `_format_data_badges`, `_format_video_metadata`, `_summarize_batch_data`
- **Tree Builder**: `_refresh_pipeline_video_table`, `_populate_video_selector_tree`, `_populate_reports_tree_from_hierarchy`
- **Event Handler**: `_on_project_overview_tree_double_click_impl`, `_on_processing_reports_item_double_click`, `_on_processing_reports_generate_partial`, `_on_report_item_select`, `_on_report_item_double_click`

### Por Status

- **LEGACY** (2): `_refresh_pipeline_video_table`, `update_reports_tree`
- **Ativo** (32): Todos os outros

---

## Nota Importante: Método Não Encontrado

O método `_build_status_token` mencionado na linha 1590 **não foi encontrado**. A linha 1590 contém apenas dados estruturais de um dicionário. Possivelmente o usuário quis referir-se a:

- `_format_status_token` (linha 3585) - método estático
- `_build_status_icon_legend` (linha 426)
- `_build_day_title` (linha 3443)

---

## Importações Globais Necessárias

Para suportar estes métodos em um novo componente `ProjectViewManager`, as seguintes importações seriam necessárias:

```python
from collections import Counter, defaultdict
from pathlib import Path
import os
import structlog
from tkinter import ttk, StringVar, messagebox
from zebtrack.core.processing_mode import ProcessingReport
from zebtrack.core.detector import ZoneData
import subprocess
```

## Constantes Globais Necessárias

- `PROJECT_STATUS_META` (dict)
- `STATUS_SYMBOLS` (dict)

## Componentes/Widgets Dependentes

- `ProjectOverviewWidget`
- `ProcessingReportsWidget`
- `CanvasManager`
- `MenuManager`
- `EventDispatcher`
- `ApplicationController` / `ProjectManager`

---

## Conclusão

Estes 34 métodos formam o núcleo da lógica de visualização e atualização de projeto na interface gráfica. A maioria está relacionada a:

1. **Atualização de árvores** (7 métodos)
2. **Formatação de dados** (7 métodos)
3. **Manipulação de eventos** (8 métodos)
4. **Orquestração de refresh** (4 métodos)
5. **Utilitários diversos** (8 métodos)

Um novo componente `ProjectViewManager` consolidaria estes métodos em um único ponto de controle, reduzindo o tamanho da classe `ApplicationGUI` e melhorando a manutenibilidade.
