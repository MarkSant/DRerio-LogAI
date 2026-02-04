# DialogManager - Guia de Migração

**Data**: 2025-11-05
**Objetivo**: Facilitar refatoração de gui.py para usar DialogManager

## Visão Geral

Este documento lista todos os métodos que precisam ser refatorados em `gui.py` para usar o novo `DialogManager`.

## 1. Setup do DialogManager

### Adicionar ao `__init__` de ApplicationGUI

```python
# Em src/zebtrack/ui/gui.py, linha ~206
# Após inicialização de outros managers:

self.menu_manager = MenuManager(self)
self.canvas_manager = CanvasManager(self)
self.state_synchronizer = StateSynchronizer(self)
self.event_dispatcher = EventDispatcher(self)
self.dialog_manager = DialogManager(self)  # ← ADICIONAR ESTA LINHA
```

## 2. Substituir Chamadas Diretas

### 2.1 MessageBox - Substituições Simples

| Linha | Método Original | Substituir Por |
| ------- | ---------------- | ---------------- |
| 7889 | `show_error(title, message)` | `self.dialog_manager.show_error(title, message)` |
| 7893 | `show_warning(title, message)` | `self.dialog_manager.show_warning(title, message)` |
| 7897 | `show_info(title, message)` | `self.dialog_manager.show_info(title, message)` |
| 7929 | `ask_ok_cancel(title, message)` | `self.dialog_manager.ask_ok_cancel(title, message)` |
| 7933 | `ask_string(title, prompt, initialvalue)` | `self.dialog_manager.ask_string(title, prompt, initialvalue)` |
| 7937 | `ask_directory(title)` | `self.dialog_manager.ask_directory(title)` |
| 7941 | `ask_open_filenames(title, filetypes)` | `self.dialog_manager.ask_open_filenames(title, filetypes)` |
| 8143 | `ask_save_filename(**options)` | `self.dialog_manager.ask_save_filename(**options)` |

**Estratégia**: Criar properties de compatibilidade temporária:

```python
# No final de gui.py, adicionar:
@property
def show_error(self):
    return self.dialog_manager.show_error

@property
def show_warning(self):
    return self.dialog_manager.show_warning

# ... etc para todos os métodos acima
```

### 2.2 Calibration - Linhas 843-860

**ANTES:**

```python
def _open_global_calibration_window(self):
    with self.controller.global_calibration_session():
        CalibrationDialog(self.root, self.controller)

def _open_project_calibration_window(self):
    if not getattr(self.controller.project_manager, "project_path", None):
        self.show_warning(
            "Nenhum Projeto",
            "Abra um projeto antes de ajustar a calibração específica.",
        )
        return

    with self.controller.project_calibration_session():
        CalibrationDialog(self.root, self.controller)
    self.update_openvino_checkbox(self.controller.use_openvino)
    self.set_active_weight_in_dropdown(self.controller.active_weight_name)
    self.update_openvino_status_display(self.controller.get_openvino_status())
```

**DEPOIS:**

```python
def _open_global_calibration_window(self):
    self.dialog_manager.open_global_calibration_window()

def _open_project_calibration_window(self):
    self.dialog_manager.open_project_calibration_window()
```

**Ação**: Remover métodos e substituir por delegação direta.

### 2.3 External Trigger Notice - Linhas 1749-1800

**ANTES:**

```python
def show_external_trigger_notice(self, session_label: str, **details):
    # 32 linhas de código...

def clear_external_trigger_notice(self):
    # 21 linhas de código...
```

**DEPOIS:**

```python
def show_external_trigger_notice(self, session_label: str, **details):
    self.dialog_manager.show_external_trigger_notice(session_label, **details)

def clear_external_trigger_notice(self):
    self.dialog_manager.clear_external_trigger_notice()
```

**Ação**: Substituir por delegação (manter métodos para compatibilidade).

### 2.4 Zone Reuse Offer - Linha 3837

**ANTES (60 linhas):**

```python
def _maybe_offer_zone_reuse(self, video_path: str) -> None:
    # ... verificações ...

    reuse = messagebox.askyesno(
        "Reutilizar zonas existentes?",
        (
            f'O vídeo "{current_name}" não possui arena ou ROIs salvas.\n\n'
            f'Deseja reutilizar as zonas desenhadas para "{last_name}"?\n'
            'Escolha "Sim" para reutilizar ou "Não" para começar do zero.'
        ),
        icon="question",
    )

    # ... resto da lógica ...
```

**DEPOIS:**

```python
def _maybe_offer_zone_reuse(self, video_path: str) -> None:
    # ... verificações ...

    reuse = self.dialog_manager.offer_zone_reuse(current_name, last_name)

    # ... resto da lógica ...
```

**Ação**: Substituir apenas a chamada ao messagebox.

### 2.5 Open Path in Explorer - Linha 4785

**ANTES (18 linhas):**

```python
def _open_path_in_explorer(self, target_path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(target_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_path])
        else:
            subprocess.Popen(["xdg-open", target_path])
    except Exception as exc:
        self.show_error(
            "Erro ao abrir pasta",
            (
                "Não foi possível abrir o diretório de resultados.\n"
                f"Caminho: {target_path}\n\nDetalhes: {exc}"
            ),
        )
```

**DEPOIS:**

```python
def _open_path_in_explorer(self, target_path: str) -> None:
    self.dialog_manager.open_path_in_explorer(target_path)
```

**Ação**: Substituir completamente por delegação.

### 2.6 ROI Template Dialogs - Linhas 5628-5851

#### 2.6.1 Show Template Save Dialog - Linha 5628

**ANTES (21 linhas):**

```python
def _show_template_save_dialog(
    self,
    *,
    has_arena: bool,
    has_rois: bool,
    allow_project: bool,
    initial_name: str,
) -> dict[str, Any] | None:
    dialog = SaveROITemplateDialog(
        self.root,
        default_name=initial_name,
        has_arena=has_arena,
        has_rois=has_rois,
        allow_project=allow_project,
    )

    if not dialog.result:
        return None

    return dialog.result
```

**DEPOIS:**

```python
def _show_template_save_dialog(
    self,
    *,
    has_arena: bool,
    has_rois: bool,
    allow_project: bool,
    initial_name: str,
) -> dict[str, Any] | None:
    return self.dialog_manager.show_template_save_dialog(
        has_arena=has_arena,
        has_rois=has_rois,
        allow_project=allow_project,
        initial_name=initial_name,
    )
```

#### 2.6.2 Delete ROI Template - Linha 5649

**ANTES (63 linhas com messagebox.askyesno):**

```python
def _on_delete_roi_template(self) -> None:
    # ... verificações ...

    response = messagebox.askyesno(
        "Confirmar Deleção",
        f"Tem certeza que deseja deletar o template '{template_name}'?\n\n"
        f"Localização: {template_location}\n"
        f"Arquivo: {template_file}\n\n"
        f"Esta ação não pode ser desfeita.",
        icon="warning",
    )

    if not response:
        return

    # ... resto da lógica ...
```

**DEPOIS:**

```python
def _on_delete_roi_template(self) -> None:
    # ... verificações ...

    response = self.dialog_manager.confirm_delete_roi_template(
        template_name, template_file, template_location
    )

    if not response:
        return

    # ... resto da lógica ...
```

#### 2.6.3 Import ROI Template - Linha 5713

**ANTES (43 linhas):**

```python
def _on_import_roi_template(self) -> None:
    pm = getattr(self.controller, "project_manager", None)
    if pm is None:
        return

    file_path = filedialog.askopenfilename(
        title="Importar Template de ROI para Biblioteca",
        filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
    )
    if not file_path:
        return

    try:
        metadata = pm.import_roi_template(file_path)
    except Exception as exc:
        log.error("gui.roi_templates.import_failed", error=str(exc), file=file_path)
        self.show_error("Erro ao importar", str(exc))
        return

    self._refresh_roi_templates()
    self._select_roi_template(metadata)
    template_name = metadata.get("name", Path(file_path).stem)
    message = (
        f"Template '{template_name}' adicionado à biblioteca.\n\n"
        "Use o botão 'Aplicar' para usar este template."
    )
    self.show_info("Template importado", message)
```

**DEPOIS:**

```python
def _on_import_roi_template(self) -> None:
    self.dialog_manager.import_roi_template()
```

#### 2.6.4 Import and Apply ROI Template - Linha 5742

**ANTES (110 linhas):**

```python
def _on_import_and_apply_roi_template(self) -> None:
    # ... muita lógica ...
```

**DEPOIS:**

```python
def _on_import_and_apply_roi_template(self) -> None:
    self.dialog_manager.import_and_apply_roi_template()
```

### 2.7 Analysis Dialogs - Linhas 6529-6607

#### 2.7.1 Center Periphery Analysis - Linha 6529

**ANTES (16 linhas):**

```python
def _run_center_periphery_analysis(self):
    current_arena_id = self.arena_selector_var.get()
    if not current_arena_id:
        self.show_error("Erro", "Selecione um aquário ativo e carregue os dados primeiro.")
        return

    dialog = CenterPeripheryDialog(self.root)
    if not dialog.result:
        return

    self.controller.run_center_periphery_analysis(
        arena_id=current_arena_id,
        method=dialog.result["method"],
        value=dialog.result["value"],
    )
```

**DEPOIS:**

```python
def _run_center_periphery_analysis(self):
    current_arena_id = self.arena_selector_var.get()
    if not current_arena_id:
        self.dialog_manager.show_error("Erro", "Selecione um aquário ativo e carregue os dados primeiro.")
        return

    result = self.dialog_manager.open_center_periphery_dialog()
    if not result:
        return

    self.controller.run_center_periphery_analysis(
        arena_id=current_arena_id,
        method=result["method"],
        value=result["value"],
    )
```

#### 2.7.2 Create Template ROIs - Linha 6546

**ANTES (62 linhas):**

```python
def _create_template_rois(self):
    current_arena_id = self.arena_selector_var.get()
    if not current_arena_id:
        self.show_error("Erro", "Selecione um aquário ativo primeiro.")
        return

    # ... obter dados da arena ...

    dialog = TemplateDialog(self.root)
    if not dialog.result:
        return

    # ... criar ROIs a partir do template ...
```

**DEPOIS:**

```python
def _create_template_rois(self):
    current_arena_id = self.arena_selector_var.get()
    if not current_arena_id:
        self.dialog_manager.show_error("Erro", "Selecione um aquário ativo primeiro.")
        return

    # ... obter dados da arena ...

    result = self.dialog_manager.open_template_rois_dialog()
    if not result:
        return

    # ... criar ROIs a partir do template ...
```

### 2.8 Project Workflow - Linha 7164

**ANTES (8 linhas):**

```python
def _open_project_workflow(self):
    project_path = self.ask_directory(title="Selecione uma Pasta de Projeto Existente")
    if not project_path:
        return

    self.event_dispatcher.publish_event(Events.PROJECT_OPEN, {"project_path": project_path})
```

**DEPOIS:**

```python
def _open_project_workflow(self):
    self.dialog_manager.open_project_workflow()
```

### 2.9 Single Video Config Dialog - Linha 7172

**ANTES (33 linhas):**

```python
def _on_analyze_single_video_clicked(self):
    dialog = SingleVideoConfigDialog(self.root, settings_obj=self.controller.settings)
    if not dialog.result:
        return

    source_type = dialog.result.get("source_type", "video")

    if source_type == "camera":
        # ... lógica ...
```

**DEPOIS:**

```python
def _on_analyze_single_video_clicked(self):
    result = self.dialog_manager.open_single_video_config_dialog()
    if not result:
        return

    source_type = result.get("source_type", "video")

    if source_type == "camera":
        # ... lógica ...
```

### 2.10 Single Video Processing - Linha 7382

**ANTES (50 linhas com messagebox.askyesnocancel):**

```python
def _on_start_single_video_processing_clicked(self):
    if self.edited_polygon_points:
        response = messagebox.askyesnocancel(
            "Salvar Polígono?",
            "Você deseja salvar as alterações no polígono antes de iniciar a "
            "análise?\n\n"
            "Sim: Salvar e iniciar análise\n"
            "Não: Descartar alterações e iniciar análise\n"
            "Cancelar: Voltar para edição",
        )
        if response is None:
            return
        elif response:
            self.controller.save_manual_arena(self.edited_polygon_points)
            self._clear_interactive_polygon()
        else:
            self._clear_interactive_polygon()

    # ... resto da lógica ...
```

**DEPOIS:**

```python
def _on_start_single_video_processing_clicked(self):
    if self.edited_polygon_points:
        response = self.dialog_manager.confirm_save_polygon_before_analysis()
        if response is None:
            return
        elif response:
            self.controller.save_manual_arena(self.edited_polygon_points)
            self._clear_interactive_polygon()
        else:
            self._clear_interactive_polygon()

    # ... resto da lógica ...
```

### 2.11 Progress Bar - Linha 7443

**ANTES (14 linhas):**

```python
def show_progress_bar(self):
    if self.progress_frame and not self.progress_frame.winfo_viewable():
        # ... lógica ...
```

**DEPOIS:**

```python
def show_progress_bar(self):
    self.dialog_manager.show_progress_bar()
```

### 2.12 Pending Videos Dialog - Linha 7901

**ANTES (28 linhas):**

```python
def show_pending_videos_dialog(
    self,
    *,
    ready_with_trajectory: list[dict],
    ready_with_zones: list[dict],
    arena_only: list[dict],
    without_arena: list[dict],
) -> dict | None:
    self.apply_pending_readiness_snapshot(
        ready_with_trajectory=ready_with_trajectory,
        ready_with_zones=ready_with_zones,
        arena_only=arena_only,
        without_arena=without_arena,
    )

    dialog = PendingVideosDialog(
        self.root,
        hierarchy_builder=self._build_video_hierarchy_snapshot,
        ready_with_trajectory=ready_with_trajectory,
        ready_with_zones=ready_with_zones,
        arena_only=arena_only,
        without_arena=without_arena,
    )

    return dialog.result
```

**DEPOIS:**

```python
def show_pending_videos_dialog(
    self,
    *,
    ready_with_trajectory: list[dict],
    ready_with_zones: list[dict],
    arena_only: list[dict],
    without_arena: list[dict],
) -> dict | None:
    return self.dialog_manager.show_pending_videos_dialog(
        ready_with_trajectory=ready_with_trajectory,
        ready_with_zones=ready_with_zones,
        arena_only=arena_only,
        without_arena=without_arena,
    )
```

### 2.13 Recording Details - Linha 8158

**ANTES (14 linhas):**

```python
def ask_recording_details_unified(self):
    pm = self.controller.project_manager
    if not pm.project_data.get("experiment_days"):
        self.show_error(
            "Error",
            "This project is not configured for live experimental tracking.",
        )
        return None

    dialog = StartRecordingDialog(self.root, pm)
    return dialog.result
```

**DEPOIS:**

```python
def ask_recording_details_unified(self):
    return self.dialog_manager.ask_recording_details_unified()
```

### 2.14 Missing Metadata - Linha 8172

**ANTES (4 linhas):**

```python
def ask_missing_metadata(self, experiment_id):
    dialog = MissingMetadataDialog(self.root, experiment_id)
    return dialog.result
```

**DEPOIS:**

```python
def ask_missing_metadata(self, experiment_id):
    return self.dialog_manager.ask_missing_metadata(experiment_id)
```

### 2.15 Remove ROI - Linha 8095

**ANTES (com messagebox.askyesno inline):**

```python
def _on_remove_roi_from_context_menu(self):
    # ... obter ROI selecionada ...

    confirm = messagebox.askyesno(
        "Confirmar Remoção",
        f"Tem certeza que deseja remover a ROI '{roi_name}'?\n\n"
        "Esta ação não pode ser desfeita.",
        icon="warning",
    )

    if confirm:
        # ... remover ROI ...
```

**DEPOIS:**

```python
def _on_remove_roi_from_context_menu(self):
    # ... obter ROI selecionada ...

    confirm = self.dialog_manager.confirm_remove_roi(roi_name)

    if confirm:
        # ... remover ROI ...
```

## 3. Checklist de Refatoração

### Fase 1: Setup ✅

- [ ] Adicionar `self.dialog_manager = DialogManager(self)` em `__init__`
- [ ] Importar `DialogManager` no início do arquivo
- [ ] Executar testes básicos

### Fase 2: Properties de Compatibilidade

- [ ] Criar properties para métodos simples (show_error, show_warning, etc.)
- [ ] Testar compatibilidade com código existente

### Fase 3: Refatoração de Métodos

- [ ] Refatorar `_open_global_calibration_window()` e `_open_project_calibration_window()`
- [ ] Refatorar `show_external_trigger_notice()` e `clear_external_trigger_notice()`
- [ ] Refatorar `_maybe_offer_zone_reuse()`
- [ ] Refatorar `_open_path_in_explorer()`
- [ ] Refatorar métodos de ROI templates (4 métodos)
- [ ] Refatorar dialogs de análise (2 métodos)
- [ ] Refatorar `_open_project_workflow()`
- [ ] Refatorar `_on_analyze_single_video_clicked()`
- [ ] Refatorar `_on_start_single_video_processing_clicked()`
- [ ] Refatorar `show_progress_bar()`
- [ ] Refatorar `show_pending_videos_dialog()`
- [ ] Refatorar `ask_recording_details_unified()`
- [ ] Refatorar `ask_missing_metadata()`
- [ ] Refatorar `_on_remove_roi_from_context_menu()`

### Fase 4: Testes

- [ ] Executar suite completa de testes
- [ ] Testar workflows de usuário manualmente
- [ ] Verificar logs para erros

### Fase 5: Limpeza

- [ ] Remover métodos antigos de gui.py (após verificação completa)
- [ ] Remover imports não utilizados
- [ ] Executar ruff check e fix
- [ ] Atualizar documentação

## 4. Métricas Esperadas

| Métrica | Antes | Depois | Redução |
| --------- | ------- | -------- | --------- |
| Linhas em gui.py | 8,286 | ~7,574 | ~712 (-8.6%) |
| Métodos em gui.py | 254 | ~222 | ~32 (-12.6%) |
| Complexidade | Alta | Média | Melhor manutenibilidade |

## 5. Riscos e Mitigações

| Risco | Mitigação |
| ------- | ----------- |
| Quebrar código existente | Criar properties de compatibilidade |
| Regressão em testes | Executar suite completa após cada mudança |
| Dependências circulares | DialogManager não deve importar gui.py |
| Perda de funcionalidade | Testar manualmente workflows críticos |

## 6. Referências

- **Arquivo original**: `src/zebtrack/ui/gui.py`
- **Novo componente**: `src/zebtrack/ui/components/dialog_manager.py`
- **Análise**: `docs/EXTRACTION_ANALYSIS_PHASE2.md`
- **Resumo**: `docs/DIALOG_MANAGER_EXTRACTION.md`
