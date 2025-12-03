# API Stability Contract (v4.0)

**Versão:** 4.0.0
**Status:** Stable
**Última Atualização:** 23/11/2025

Este documento define a API pública da classe `ApplicationGUI` (`src/zebtrack/ui/gui.py`).
Com a refatoração v4.0, a API pública foi drasticamente reduzida, delegando responsabilidades para componentes internos. Apenas métodos essenciais para inicialização, ciclo de vida e feedback global permanecem.

## Métodos Públicos (Core API)

Estes métodos são considerados estáveis e seguros para uso por componentes externos (como `MainController` ou scripts de entrada).

### 1. Ciclo de Vida e Inicialização

*   `__init__(root, controller, event_bus=None, settings_obj=None)`
    *   Inicializa a aplicação, constrói componentes e configura o `UICoordinator`.

### 2. Feedback ao Usuário (Delegates)

Estes métodos delegam para `DialogManager`, mantendo uma fachada conveniente para mensagens globais.

*   `show_error(title, message)`
*   `show_warning(title, message)`
*   `show_info(title, message)`
*   `ask_ok_cancel(title, message)`
*   `ask_string(title, prompt, initialvalue=None)`
*   `ask_directory(title)`
*   `ask_open_filenames(title, filetypes)`
*   `ask_save_filename(**options)`

### 3. Status e Progresso

Métodos para atualizar a barra de status e progresso global.

*   `set_status(text)`
*   `show_progress_bar()`
*   `hide_progress_bar()`
*   `update_progress(value)`
*   `update_idletasks()`

### 4. Controle de Estado da UI

*   `update_button_state(button_name, state)`
    *   Controla habilitação de botões globais (Gravar, Processar, Parar).

### 5. Interfaces Específicas (Wizards/Dialogs Complexos)

*   `ask_recording_details_unified()`
*   `ask_missing_metadata(experiment_id)`
*   `show_pending_videos_dialog(...)`

### 6. Métodos de Integração com Controller (Callbacks)

Estes métodos são chamados pelo Controller para atualizar a visualização em tempo real.

*   `update_weights_dropdown(weights)`
*   `set_active_weight_in_dropdown(weight_name)`
*   `update_openvino_checkbox(enabled)`
*   `update_openvino_status_display(status)`
*   `update_gpu_hardware_display(hardware_summary)`
*   `update_detection_overlay(detections, report)`
*   `update_processing_mode(report)`
*   `update_analysis_profile(profile_name)`
*   `update_analysis_progress(value, status_text)`
*   `update_analysis_metadata(metadata)`
*   `setup_zone_definition_for_single_video(video_path, config)`

---

## Métodos Removidos/Migrados (v3 -> v4)

Os seguintes métodos **NÃO** fazem mais parte da API pública da GUI e foram movidos para componentes especializados ou substituídos por eventos:

*   `update_zone_listbox` → `UIEvents.ZONES_UPDATED`
*   `refresh_project_views` → `UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED`
*   `apply_pending_readiness_snapshot` → `UIEvents.READINESS_SNAPSHOT_UPDATED`
*   `_edit_selected_zone_vertices` → `CanvasManager.edit_selected_zone_vertices`
*   `_on_canvas_click` → `CanvasEventHandler`
*   `_format_day_display` → `ValidationManager`
*   `_pipeline_summary_exists` → `ProjectViewManager`
*   `_generate_unified_report` → `ProjectViewManager`

## Política de Mudanças

1.  Novos métodos públicos na `GUI` devem ser evitados. Prefira adicionar lógica aos Managers (`CanvasManager`, etc.) ou `UICoordinator`.
2.  Comunicação entre componentes deve ocorrer EXCLUSIVAMENTE via `EventBusV2`.
3.  A `GUI` deve atuar apenas como container e ponto de injeção de dependência.