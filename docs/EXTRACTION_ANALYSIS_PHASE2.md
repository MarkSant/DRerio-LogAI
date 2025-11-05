# ANÁLISE DE EXTRAÇÃO: gui.py → 4 COMPONENTES

## RESUMO EXECUTIVO
- **Arquivo atual**: gui.py (8286 linhas, 254 métodos)
- **Métodos já extraídos**: MenuManager, CanvasManager, StateSynchronizer, EventDispatcher
- **Componentes propostos**: DialogManager, ValidationManager, WidgetFactory, ProjectViewManager
- **Linhas estimadas para extrair**: ~2,400 linhas (28% do arquivo)

---

## 1. DIALOG MANAGER (~800 linhas)

### Descrição
Gerencia todos os diálogos, caixas de mensagem e janelas de entrada do usuário.

### Métodos a Extrair (20 métodos)

| Linha | Método | Descrição | Linhas |
|-------|--------|-----------|--------|
| 843 | `_open_global_calibration_window()` | Abre diálogo de calibração global | 4 |
| 847 | `_open_project_calibration_window()` | Abre diálogo de calibração de projeto | 14 |
| 1749 | `show_external_trigger_notice()` | Exibe aviso de trigger externo | 32 |
| 1781 | `clear_external_trigger_notice()` | Limpa aviso de trigger | 21 |
| 3837 | `_maybe_offer_zone_reuse()` | Oferece reutilizar zonas com messagebox.askyesno | 60 |
| 4785 | `_open_path_in_explorer()` | Abre caminho no explorador de arquivos | 18 |
| 5628 | `_show_template_save_dialog()` | Abre SaveROITemplateDialog | 21 |
| 7164 | `_open_project_workflow()` | Abre diálogo de workflow do projeto | 8 |
| 7443 | `show_progress_bar()` | Mostra barra de progresso | 14 |
| 7889 | `show_error()` | Exibe messagebox de erro | 4 |
| 7893 | `show_warning()` | Exibe messagebox de aviso | 4 |
| 7897 | `show_info()` | Exibe messagebox de informação | 4 |
| 7901 | `show_pending_videos_dialog()` | Abre PendingVideosDialog | 28 |
| 7929 | `ask_ok_cancel()` | Dialogo Sim/Não/Cancelar | 4 |
| 7933 | `ask_string()` | Diálogo para entrada de string | 4 |
| 7937 | `ask_directory()` | Abre file dialog para diretório | 4 |
| 7941 | `ask_open_filenames()` | Abre file dialog para múltiplos arquivos | 5 |
| 8143 | `ask_save_filename()` | Abre file dialog para salvar arquivo | 4 |
| 8158 | `ask_recording_details_unified()` | Abre diálogo de detalhes de gravação | 14 |
| 8172 | `ask_missing_metadata()` | Abre diálogo de metadata faltante | 15 |

### Métodos Relacionados com Diálogos (ainda em gui.py)
Estes devem ser refatorados para usar DialogManager:
- `_on_save_roi_template()` (linha 5407, ~53 linhas) - abre SaveROITemplateDialog
- `_on_delete_roi_template()` (linha 5649, ~63 linhas) - usa messagebox.askyesno
- `_on_import_roi_template()` (linha 5713, ~43 linhas) - abre filedialog.askopenfilename
- `_on_import_and_apply_roi_template()` (linha 5742, ~110 linhas) - múltiplos diálogos
- `_run_center_periphery_analysis()` (linha 6529, ~16 linhas) - abre CenterPeripheryDialog
- `_create_template_rois()` (linha 6546, ~62 linhas) - abre TemplateDialog
- `_on_analyze_single_video_clicked()` (linha 7172, ~33 linhas) - múltiplos diálogos
- `_on_start_single_video_processing_clicked()` (linha 7382, ~50 linhas) - messagebox.askyesnocancel

**Total: ~600 linhas de métodos relacionados que chamarão DialogManager**

### Estimativa Total para DialogManager
- **20 métodos extraídos**: ~282 linhas
- **8 métodos refatorados**: ~430 linhas de código que chama DialogManager
- **Total**: ~712 linhas de código relacionado

---

## 2. VALIDATION MANAGER (~400 linhas)

### Descrição
Valida entradas de usuário, verificações de pré-condições, composição de configurações.

### Métodos a Extrair (5 métodos base + auxiliares)

| Linha | Método | Descrição | Linhas |
|-------|--------|-----------|--------|
| 1416 | `_compose_overview_status_line()` | Compõe string de status do resumo | 17 |
| 1490 | `_prepare_overview_hierarchy_for_widget()` | Prepara hierarquia para exibição (COMPLEXO) | 113 |
| 6803 | `_check_live_project_calibration()` | Valida calibração do projeto ao vivo | 35 |
| 7254 | `_prepare_single_video_ui_state()` | Prepara estado de UI para vídeo único | 40 |
| 7294 | `_compose_single_video_runtime_config()` | Compõe e valida configuração de tempo de execução | 45 |

### Métodos que Precisam de Validação (Refatoração)
Estes contêm lógica de validação a extrair:
- `_on_auto_detect_clicked()` (linha 7339, ~42 linhas) - valida stabilization_frames >= 0
- `_compose_single_video_runtime_config()` (linha 7294, ~45 linhas) - valida inteiros positivos
- `_get_zone_data_for_active_context()` (linha 5542, ~60 linhas) - valida zona ativa

**Métodos com validações inline (em diálogos):**
- `_on_save_roi_template()` - valida zone_data/polygon
- `_on_import_and_apply_roi_template()` - valida video selecionado
- `_on_delete_roi_template()` - valida template selecionado
- `_run_center_periphery_analysis()` - valida arena_id
- `_create_template_rois()` - valida arena_id e polygon

### Estimativa Total para ValidationManager
- **5 métodos extraídos**: ~250 linhas
- **~15 métodos refatorados**: ~400 linhas que chamarão ValidationManager
- **Total**: ~650 linhas

---

## 3. WIDGET FACTORY (~600 linhas)

### Descrição
Criação de widgets complexos, frames, abas e painéis da UI.

### Métodos a Extrair (29 métodos - EXCLUINDO já extraídos)

**Nota**: MenuManager, CanvasManager já extraíram métodos de criação de menus e canvas.
Estes são métodos restantes que precisam ser reorganizados.

| Linha | Método | Descrição | Linhas |
|-------|--------|-----------|--------|
| 426 | `_build_status_icon_legend()` | Constrói legenda de status | 14 |
| 592 | `_create_welcome_frame()` | Cria frame de boas-vindas | 27 |
| 632 | `_build_project_actions()` | Constrói botões de ações do projeto | 26 |
| 658 | `_build_model_status()` | Constrói exibição de status do modelo | 18 |
| 882 | `_create_main_control_frame()` | Cria frame principal de controles | 42 |
| 924 | `_create_configuration_tab_widget()` | Cria aba de configuração | 29 |
| 1105 | `_create_main_controls_tab()` | Cria aba controle principal (GRANDE) | 118 |
| 1223 | `_create_project_overview_panel()` | Cria painel resumo do projeto | 51 |
| 1802 | `_create_roi_analysis_tab()` | Cria aba análise ROI | 58 |
| 1990 | `_create_zone_control_widgets()` | Cria widgets controle de zonas (MUITO GRANDE) | 386 |
| 2376 | `_create_zone_summary_cards_section()` | Cria seção de cards de resumo | 74 |
| 2450 | `_create_pipeline_processing_tab()` | Cria aba pipeline de processamento | 115 |
| 2967 | `_create_analysis_tab_widget()` | Cria aba análise | 36 |
| 3003 | `_create_scrollable_controls_frame()` | Cria frame com scroll | 32 |
| 3443 | `_build_day_title()` | Constrói título de dia | 17 |
| 3460 | `_build_video_hierarchy_data()` | Constrói hierarquia de vídeos (dados) | 66 |
| 3526 | `_build_video_hierarchy_snapshot()` | Constrói snapshot da hierarquia | 59 |
| 3902 | `_create_reports_tab()` | Cria aba relatórios (LEGACY) | 65 |
| 3967 | `_create_processing_reports_tab()` | Cria aba processamento e relatórios | 44 |
| 4307 | `_build_processing_report_artifact_id()` | Constrói ID de artefato | 6 |
| 4453 | `_build_report_hierarchy()` | Constrói hierarquia de relatórios | 50 |
| 4983 | `_create_drawing_buttons()` | Cria botões de desenho | 29 |
| 5495 | `_build_roi_template_identifier()` | Constrói identificador de template | 13 |
| 6546 | `_create_template_rois()` | Cria ROIs a partir de template (dialog) | 62 |
| 6786 | `_create_progress_grid_tab()` | Cria aba grid de progresso | 17 |
| 7139 | `_create_project_workflow()` | Cria workflow do projeto | 25 |
| 7681 | `_build_track_options()` | Constrói opções de track | 16 |
| 953 | `_reload_config_editor_values_widget()` | Recarrega valores do editor de config | 51 |
| 1004 | `_on_reset_global_config_form_widget()` | Handler reset de config (PODE IR PARA EVENT DISPATCHER) | 9 |
| 1012 | `_on_save_global_config_from_widget()` | Handler save de config (PODE IR PARA EVENT DISPATCHER) | 18 |

### Métodos Auxiliares (Helpers de Layout)
- `_on_pane_configure()` (linha 1860, ~37 linhas) - configuração de pane
- `_on_frame_configure()` (linha 3035, ~4 linhas) - configuração de frame
- `_on_canvas_configure()` (linha 1962, ~20 linhas) - configuração de canvas
- `_on_canvas_configure_scroll()` (linha 3039, ~4 linhas) - configuração de scroll

### Métodos que Precisam Refatoração
- `_on_roi_rule_change_widget()` (linha 1099) - atualiza UI baseado em mudança
- `_on_roi_rule_change()` (linha 3083) - handler de mudança de regra

### Estimativa Total para WidgetFactory
- **27 métodos principais extraídos**: ~1,400 linhas
- **4-5 métodos auxiliares**: ~100 linhas
- **Total**: ~1,500 linhas

---

## 4. PROJECT VIEW MANAGER (~500 linhas)

### Descrição
Gerencia visualizações de projeto, navegação entre views, atualização de árvores e refresh de dados.

### Métodos a Extrair (28 métodos)

| Linha | Método | Descrição | Linhas |
|-------|--------|-----------|--------|
| 1274 | `_navigate_to_processing_reports_tab()` | Navega para aba de relatórios | 16 |
| 1303 | `_request_overview_refresh()` | Solicita refresh de overview (agendado) | 27 |
| 1330 | `refresh_project_views()` | Atualiza overview, pipeline e reports | 33 |
| 1363 | `_refresh_project_overview()` | Atualiza painel de resumo do projeto | 53 |
| 1433 | `_update_project_overview_summary()` | Atualiza sumário do overview | 35 |
| 1468 | `_update_project_overview_tree()` | Atualiza árvore de overview | 22 |
| 1688 | `_on_project_overview_tree_double_click()` | Handler duplo clique em tree | 11 |
| 1699 | `_on_project_overview_tree_double_click_impl()` | Implementação do duplo clique | 33 |
| 1732 | `_on_project_overview_right_click()` | Handler botão direito em tree | 17 |
| 2633 | `_refresh_pipeline_video_table()` | Atualiza tabela pipeline de vídeos | 48 |
| 2856 | `_resolve_processing_reports_video_paths()` | Resolve caminhos de vídeos selecionados | 21 |
| 2894 | `_update_pipeline_buttons_state()` | Atualiza estado de botões pipeline | 19 |
| 3589 | `_populate_video_selector_tree()` | Popula árvore seletor de vídeos | 48 |
| 3720 | `_refresh_video_selector_tree()` | Atualiza árvore seletor de vídeos | 22 |
| 4011 | `_on_processing_reports_item_double_click()` | Handler duplo clique em reports | 45 |
| 4056 | `_on_processing_reports_generate_partial()` | Handler gerar relatório parcial | 31 |
| 4087 | `_refresh_processing_reports_tab()` | Atualiza aba processamento/relatórios (GRANDE) | 197 |
| 4313 | `_append_processing_reports_artifacts()` | Adiciona artefatos ao relatório | 16 |
| 4379 | `update_reports_tree()` | Atualiza árvore de relatórios | 50 |
| 4503 | `_populate_reports_tree_from_hierarchy()` | Popula árvore de relatórios (COMPLEXO) | 111 |
| 4614 | `_append_report_artifacts()` | Adiciona artefatos ao relatório | 56 |
| 4670 | `_on_report_item_select()` | Handler seleção de item relatório | 16 |
| 4686 | `_on_report_item_double_click()` | Handler duplo clique relatório | 32 |
| 5853 | `_update_delete_template_button_state()` | Atualiza estado botão delete template | 11 |
| 7095 | `_refresh_openvino_summary()` | Atualiza sumário OpenVINO | 8 |
| 539 | `_update_window_title()` | Atualiza título da janela | 14 |
| 170 | `update_tree_selection()` | (TreeVideosHierarchy) Atualiza seleção | 17 |
| 1590 | `_build_status_token()` | Constrói token de status (helper) | 10 |

### Métodos Complexos de Construção de Hierarquias
- `_prepare_overview_hierarchy_for_widget()` (linha 1490, ~113 linhas) - COMPLEXO, pode ir para ValidationManager
- `_build_video_hierarchy_data()` (linha 3460, ~66 linhas) - já na categoria
- `_build_report_hierarchy()` (linha 4453, ~50 linhas) - já na categoria

### Métodos Auxiliares (Formatação de Display)
- `_format_status_label()` (linha 1603) - formata label de status
- `_format_status_summary()` (linha 1607) - formata sumário de status
- `_format_status_ratio()` (linha 1622) - formata razão de status
- `_summarize_batch_data()` (linha 1630) - resume dados do batch
- `_format_data_badges()` (linha 1652) - formata badges de dados
- `_format_video_metadata()` (linha 1668) - formata metadata do vídeo
- `_format_status_token()` (linha 3585) - formata token de status

### Estimativa Total para ProjectViewManager
- **28 métodos extraídos**: ~1,000 linhas
- **7 métodos auxiliares de formatação**: ~150 linhas
- **Total**: ~1,150 linhas

---

## RESUMO FINAL

| Componente | Métodos | Linhas Extraídas | Linhas Refatoradas | Total |
|-----------|---------|------------------|-------------------|-------|
| DialogManager | 20 | 282 | ~430 | ~712 |
| ValidationManager | 5 | 250 | ~400 | ~650 |
| WidgetFactory | 27 | 1,400 | ~100 | ~1,500 |
| ProjectViewManager | 28 | 1,000 | ~150 | ~1,150 |
| **TOTAL** | **80** | **~2,932** | **~1,080** | **~4,012** |

**Redução esperada em gui.py**: De 8286 para ~4274 linhas (48% de redução)

---

## PRIORIZAÇÃO RECOMENDADA

1. **DialogManager** (PRIMEIRA) - Menos dependências, mais direto
2. **ValidationManager** (SEGUNDA) - Suporta DialogManager e WidgetFactory
3. **WidgetFactory** (TERCEIRA) - Grande impacto na complexidade
4. **ProjectViewManager** (QUARTA) - Bastante independente, maior refatoração de UI

---

## NOTAS IMPORTANTES

### Métodos NÃO Extrair (Já Extraídos)
- MenuManager: métodos de menu, context menus
- CanvasManager: métodos de canvas, drawing, transformações
- StateSynchronizer: methods de sincronização de estado
- EventDispatcher: métodos de event bus

### Métodos que Interagem Entre Componentes
- `_on_save_roi_template()` usa DialogManager + ValidationManager
- `_on_import_and_apply_roi_template()` usa DialogManager + ValidationManager + ProjectViewManager
- `_create_main_controls_tab()` usa WidgetFactory + ProjectViewManager

### Dependências de Diálogos Já Extraídos
As seguintes classes de diálogos já existem em `ui/dialogs/`:
- CalibrationDialog
- SaveROITemplateDialog
- CenterPeripheryDialog
- TemplateDialog
- SubjectSelectionDialog
- ColorSelectionDialog
- PendingVideosDialog
- StartRecordingDialog
- MissingMetadataDialog
- SingleVideoConfigDialog

DialogManager deve gerenciar a abertura dessas dialogs.

