# Plano Detalhado: Melhorias no Fluxo Pós-Criação de Projeto

**Data de Criação:** 2025-01-06
**Status:** Planejado (aguardando implementação)
**Prioridade:** Alta

---

## PROBLEMAS IDENTIFICADOS

### 🔴 Problema 1: Canvas Completamente Vazio na Aba "Configuração de Zonas"

**Estado Atual:**
- Canvas cinza sem nenhum conteúdo visual
- Zonas importadas estão salvas em `project_data["detection_zones"]` mas não aparecem
- Usuário não sabe qual vídeo selecionar para visualizar
- Não há interface para escolher vídeo da lista do projeto

**Impacto:** Usuário não consegue visualizar nem editar zonas importadas

### 🔴 Problema 2: Falta Hierarquia Experimental nas Listagens

**Estado Atual:**
- Aba Relatórios mostra: `video_001.mp4` sem contexto
- Impossível saber: qual grupo? qual dia? qual sujeito?
- Listagens em ordem alfabética sem agrupamento lógico

**Impacto:** Usuário perde contexto experimental do estudo

### 🔴 Problema 3: Metadados Experimentais Não Persistidos

**Estado Atual:**
```python
# project.json atual
{
  "batches": [{
    "timestamp": "2025-01-06T10:30:00",
    "videos": [{
      "path": "/data/Control/Day01/Subject01.mp4",
      "sha256": "abc123...",
      "status": "processed"
      # ❌ FALTA: grupo, dia, sujeito, nome amigável
    }]
  }]
}
```

**Causa Raiz:** `detected_design` do wizard não é propagado para estrutura de vídeos

**Impacto:** Re-parsing via regex toda vez, perda de nomes amigáveis

### 🔴 Problema 4: Nomes de Grupos Não Editáveis no Wizard

**Estado Atual:**
- Wizard detecta: `["Control", "Treatment", "Group1"]`
- Editor existe mas é **opcional** (botão "Editar Design")
- Usuário não pode mapear: `"Control" → "Veículo"`, `"Treatment" → "CBD 10mg"`

**Impacto:** Relatórios científicos usam códigos ao invés de nomes descritivos

---

## SOLUÇÕES DETALHADAS

### ✅ Solução 1: Seletor de Vídeos com Hierarquia e Simbologias

#### 1.1. Wireframe da Interface

```
┌─ Configuração de Zonas ──────────────────────────────────────────┐
│                                                                   │
│ ┌─ Selecionar Vídeo para Desenho ───────────────────────────┐   │
│ │                                                             │   │
│ │  🔍 Buscar: [___________] 🔄 Atualizar                     │   │
│ │                                                             │   │
│ │  ▼ 🏷️ Controle (Control) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │   │
│ │    ▼ 📅 Dia 01 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │   │
│ │      🐟 Sujeito 01  🟢🟢🟢  video_001.mp4                   │   │
│ │      🐟 Sujeito 02  🟢🟢⚫  video_002.mp4                   │   │
│ │    ▶ 📅 Dia 02 (2 vídeos)                                  │   │
│ │  ▼ 🏷️ CBD 10mg (Treatment) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │   │
│ │    ▼ 📅 Dia 01 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │   │
│ │      🐟 Sujeito 01  🟢🟢🟢  video_010.mp4                   │   │
│ │      🐟 Sujeito 02  ⚫⚫⚫  video_011.mp4                   │   │
│ │    ▶ 📅 Dia 02 (2 vídeos)                                  │   │
│ │  ▶ 🏷️ Grupo Experimental (Group1) (8 vídeos)              │   │
│ │                                                             │   │
│ │  [📹 Carregar Frame do Vídeo Selecionado]                  │   │
│ │                                                             │   │
│ │  Legenda: 🟢 Arena | 🟢 ROIs | 🟢 Trajetória               │   │
│ │           ⚫ = Não disponível                               │   │
│ └─────────────────────────────────────────────────────────────┘   │
│                                                                   │
│ ┌─ Canvas de Desenho ────────────────────────────────────────┐   │
│ │                                                             │   │
│ │          [Frame do vídeo selecionado com zonas]            │   │
│ │                                                             │   │
│ └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

#### 1.2. Símbolos de Status (Detalhado)

```python
STATUS_SYMBOLS = {
    "arena": {
        "available": "🟢",  # Verde - Arena disponível
        "missing": "⚫",    # Preto - Sem arena
    },
    "rois": {
        "available": "🟢",  # Verde - ROIs disponíveis
        "missing": "⚫",    # Preto - Sem ROIs
    },
    "trajectory": {
        "available": "🟢",  # Verde - Trajetória completa
        "missing": "⚫",    # Preto - Sem trajetória
    }
}

# Exemplo de display:
# "🐟 Sujeito 01  🟢🟢🟢  video_001.mp4" = Arena + ROIs + Trajetória
# "🐟 Sujeito 02  🟢🟢⚫  video_002.mp4" = Arena + ROIs, sem trajetória
# "🐟 Sujeito 03  🟢⚫⚫  video_003.mp4" = Só arena
# "🐟 Sujeito 04  ⚫⚫⚫  video_004.mp4" = Nada processado
```

#### 1.3. Implementação - `gui.py`

**Localização:** `_create_zone_control_widgets()` após linha 1836

**Código Completo:**

```python
# === Video Selector Widget ===
video_selector_frame = ttk.LabelFrame(
    self.zone_controls_frame,
    text="📹 Selecionar Vídeo para Desenho",
    padding=10
)
video_selector_frame.pack(fill="x", pady=5)

# Search bar
search_frame = ttk.Frame(video_selector_frame)
search_frame.pack(fill="x", pady=(0, 5))

ttk.Label(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 5))
self.video_search_var = StringVar()
self.video_search_var.trace("w", lambda *args: self._filter_video_tree())
ttk.Entry(
    search_frame,
    textvariable=self.video_search_var,
    width=25
).pack(side="left", fill="x", expand=True, padx=(0, 5))
ttk.Button(
    search_frame,
    text="🔄",
    width=3,
    command=self._populate_video_selector_tree
).pack(side="left")

# Hierarchical TreeView
tree_container = ttk.Frame(video_selector_frame)
tree_container.pack(fill="both", expand=True)

self.video_selector_tree = ttk.Treeview(
    tree_container,
    columns=("status", "filename"),
    show="tree headings",
    height=10,
    selectmode="browse"
)
self.video_selector_tree.heading("#0", text="Hierarquia")
self.video_selector_tree.heading("status", text="Dados")
self.video_selector_tree.heading("filename", text="Arquivo")

# Column widths
self.video_selector_tree.column("#0", width=200, stretch=True)
self.video_selector_tree.column("status", width=80, stretch=False)
self.video_selector_tree.column("filename", width=150, stretch=True)

scrollbar = ttk.Scrollbar(
    tree_container,
    orient="vertical",
    command=self.video_selector_tree.yview
)
self.video_selector_tree.configure(yscrollcommand=scrollbar.set)
self.video_selector_tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# Double-click to load
self.video_selector_tree.bind("<Double-Button-1>", self._on_video_tree_double_click)

# Load button
ttk.Button(
    video_selector_frame,
    text="📹 Carregar Frame do Vídeo Selecionado",
    command=self._load_selected_video_frame
).pack(pady=(5, 0))

# Legend
legend_frame = ttk.Frame(video_selector_frame)
legend_frame.pack(fill="x", pady=(5, 0))
ttk.Label(
    legend_frame,
    text="Legenda: 🟢 Arena | 🟢 ROIs | 🟢 Trajetória | ⚫ Não disponível",
    font=("TkDefaultFont", 8),
    foreground="gray"
).pack()
```

**Nova Função `_populate_video_selector_tree()`:**

```python
def _populate_video_selector_tree(self):
    """Popula árvore hierárquica de vídeos (Grupo > Dia > Sujeito)."""

    # Clear existing
    for item in self.video_selector_tree.get_children():
        self.video_selector_tree.delete(item)

    if not self.controller.project_manager.project_path:
        return

    # Get all videos with metadata
    all_videos = self.controller.project_manager.get_all_videos()

    # Group by: group > day > subject
    hierarchy = {}
    for video in all_videos:
        metadata = video.get("metadata", {})
        group = metadata.get("group", "Sem Grupo")
        group_display = metadata.get("group_display_name", group)
        day = metadata.get("day", "Sem Dia")
        subject = metadata.get("subject", "Desconhecido")

        # Build hierarchy dict
        if group not in hierarchy:
            hierarchy[group] = {"display": group_display, "days": {}}
        if day not in hierarchy[group]["days"]:
            hierarchy[group]["days"][day] = []

        hierarchy[group]["days"][day].append(video)

    # Populate tree
    for group_id, group_data in sorted(hierarchy.items()):
        group_display = group_data["display"]
        total_videos = sum(len(vids) for vids in group_data["days"].values())

        # Insert group node
        group_node = self.video_selector_tree.insert(
            "",
            "end",
            text=f"🏷️ {group_display} ({group_id})",
            values=("", f"{total_videos} vídeos"),
            open=True  # Expanded by default
        )

        # Insert days
        for day, videos in sorted(group_data["days"].items()):
            day_node = self.video_selector_tree.insert(
                group_node,
                "end",
                text=f"📅 Dia {day}",
                values=("", f"{len(videos)} vídeos"),
                open=False  # Collapsed by default
            )

            # Insert videos
            for video in sorted(videos, key=lambda v: v.get("metadata", {}).get("subject", 0)):
                subject = video["metadata"].get("subject", "?")
                filename = os.path.basename(video["path"])

                # Build status symbols
                has_arena = video.get("has_arena", False)
                has_rois = video.get("has_rois", False)
                has_trajectory = video.get("has_trajectory", False)

                status = (
                    ("🟢" if has_arena else "⚫") +
                    ("🟢" if has_rois else "⚫") +
                    ("🟢" if has_trajectory else "⚫")
                )

                # Insert video node (store full path in tags)
                self.video_selector_tree.insert(
                    day_node,
                    "end",
                    text=f"🐟 Sujeito {subject:02d}",
                    values=(status, filename),
                    tags=(video["path"],)  # Store path for retrieval
                )

    log.info(
        "gui.video_selector.populated",
        groups=len(hierarchy),
        total_videos=len(all_videos)
    )
```

**Nova Função `_load_selected_video_frame()`:**

```python
def _load_selected_video_frame(self):
    """Carrega frame do vídeo selecionado no canvas e desenha zonas."""

    selection = self.video_selector_tree.selection()
    if not selection:
        self.show_warning(
            "Nenhum Vídeo Selecionado",
            "Por favor, selecione um vídeo da lista para carregar."
        )
        return

    # Get video path from tags
    item_id = selection[0]
    tags = self.video_selector_tree.item(item_id, "tags")

    if not tags:
        # User selected group/day node, not video
        self.show_info(
            "Selecione um Vídeo",
            "Por favor, selecione um vídeo específico (🐟), não um grupo ou dia."
        )
        return

    video_path = tags[0]

    # Load frame to canvas
    success = self.load_video_frame_to_canvas(video_path, frame_number=0)

    if success:
        # Redraw zones from project data
        self.redraw_zones_from_project_data()

        # Update status
        filename = os.path.basename(video_path)
        self.set_status(f"✓ Frame carregado: {filename}")

        log.info("gui.video_selector.frame_loaded", path=video_path)
    else:
        self.show_error(
            "Erro ao Carregar",
            f"Não foi possível carregar o vídeo:\n{video_path}"
        )

def _on_video_tree_double_click(self, event):
    """Handle double-click on video tree."""
    self._load_selected_video_frame()

def _filter_video_tree(self):
    """Filtra árvore baseado no texto de busca."""
    search_text = self.video_search_var.get().lower()

    if not search_text:
        # Show all - repopulate
        self._populate_video_selector_tree()
        return

    # Re-populate with filtering logic
    # (Simplified: rebuild tree with filtered items)
    self._populate_video_selector_tree()
```

**Chamar população ao abrir projeto:**

Em `_load_project_view()` após linha 3833:

```python
elif project_type == "pre-recorded":
    self.update_reports_tree()
    self._populate_video_selector_tree()  # ← ADICIONAR AQUI
    self.set_status(f"Projeto: {pm.get_project_name()} - Pronto.")
```

---

### ✅ Solução 2: Persistir Metadados Experimentais

#### 2.1. Nova Estrutura de Dados

**Arquivo:** `src/zebtrack/core/project_manager.py`

**Modificar função `add_video_batch()` linha ~602:**

```python
def add_video_batch(self, video_files: list[dict], save_project: bool = True):
    """
    Adds a new batch of videos to the project.

    Args:
        video_files: A list of video dicts from scan_input_paths.
                     Now expects additional fields:
                     - group (str): Experimental group ID
                     - group_display_name (str): Friendly group name
                     - day (str|int): Day/timepoint ID
                     - subject (str|int): Subject/animal ID
        save_project: Whether to save the project file after adding.
    """
    if not video_files:
        return

    new_batch = {
        "timestamp": datetime.now().isoformat(),
        "videos": [],
    }

    for video_info in video_files:
        video_path = video_info["path"]
        video_hash = calculate_sha256(video_path)

        # Extract metadata
        metadata = {
            "group": video_info.get("group"),
            "group_display_name": video_info.get("group_display_name"),
            "day": video_info.get("day"),
            "subject": video_info.get("subject"),
        }

        video_entry = {
            "path": video_path,
            "sha256": video_hash,
            "status": "processed" if video_info.get("has_data") else "pending",
            "metadata": metadata,  # ← NOVO
            # Parquet availability flags (for quick lookup)
            "has_arena": video_info.get("has_arena", False),
            "has_rois": video_info.get("has_rois", False),
            "has_trajectory": video_info.get("has_trajectory", False),
        }

        new_batch["videos"].append(video_entry)

    self.project_data.setdefault("batches", []).append(new_batch)
    log.info(
        "project.batch.added",
        count=len(video_files),
        has_metadata=any(v.get("group") for v in video_files)
    )

    if save_project:
        self.save_project()
```

#### 2.2. Enriquecer Vídeos com Design ao Criar Projeto

**Arquivo:** `src/zebtrack/ui/wizard/wizard_adapter.py`

**Adicionar função (nova):**

```python
def enrich_videos_with_design_metadata(
    scanned_videos: list[dict],
    detected_design: dict | None,
    group_display_names: dict[str, str] | None = None
) -> list[dict]:
    """
    Enriquece vídeos com metadados de grupo/dia/sujeito.

    Args:
        scanned_videos: Lista de vídeos do scan_input_paths
        detected_design: Design experimental detectado
        group_display_names: Mapeamento ID → nome amigável
            Ex: {"Control": "Veículo", "Treatment": "CBD 10mg"}

    Returns:
        Lista de vídeos enriquecidos com campos:
        - group, group_display_name, day, subject
    """
    if not detected_design:
        return scanned_videos

    group_display_names = group_display_names or {}

    # Get regex patterns from detected design
    custom_patterns = detected_design.get("custom_patterns", {})
    group_pattern = custom_patterns.get("group_pattern")
    day_pattern = custom_patterns.get("day_pattern")
    subject_pattern = custom_patterns.get("subject_pattern")

    enriched_videos = []

    for video in scanned_videos:
        path = video["path"]
        enriched = video.copy()

        # Extract group
        if group_pattern:
            match = re.search(group_pattern, path)
            if match:
                group_id = match.group(1) if match.groups() else match.group(0)
                enriched["group"] = group_id
                enriched["group_display_name"] = group_display_names.get(
                    group_id, group_id
                )

        # Extract day
        if day_pattern:
            match = re.search(day_pattern, path)
            if match:
                day_id = match.group(1) if match.groups() else match.group(0)
                enriched["day"] = day_id

        # Extract subject
        if subject_pattern:
            match = re.search(subject_pattern, path)
            if match:
                subject_id = match.group(1) if match.groups() else match.group(0)
                enriched["subject"] = subject_id

        enriched_videos.append(enriched)

    log.info(
        "wizard.videos_enriched",
        total=len(enriched_videos),
        with_group=sum(1 for v in enriched_videos if v.get("group")),
        with_day=sum(1 for v in enriched_videos if v.get("day")),
        with_subject=sum(1 for v in enriched_videos if v.get("subject"))
    )

    return enriched_videos
```

**Modificar `adapt_wizard_data()` linha ~100:**

```python
def adapt_wizard_data(wizard_data: dict) -> dict:
    """..."""

    # ... código existente ...

    detected_design = wizard_data.get("detected_design")
    scanned_videos = wizard_data.get("scanned_videos", [])

    # Enrich videos with design metadata
    if detected_design and scanned_videos:
        group_display_names = detected_design.get("group_display_names", {})
        scanned_videos = enrich_videos_with_design_metadata(
            scanned_videos,
            detected_design,
            group_display_names
        )

    # ... resto do código ...

    return {
        # ... outros campos ...
        "video_files": scanned_videos,  # Now enriched!
        "_wizard_metadata": {
            # ... outros campos ...
            "scanned_videos": scanned_videos,  # Pass enriched version
        }
    }
```

---

### ✅ Solução 3: Editor de Grupos Obrigatório com Nomes Amigáveis

#### 3.1. Melhorar `DesignEditorDialog`

**Arquivo:** `src/zebtrack/ui/wizard/design_editor_dialog.py`

**Modificar estrutura de dados (linha ~58):**

```python
def __init__(self, parent, design: dict):
    self.input_design = design.copy() if design else {}
    self.edited_design = None

    # Initialize working copies
    self.groups = list(design.get("groups", []))
    self.days = list(design.get("days", [])) if design.get("days") else []
    self.subjects_per_group = {
        group: list(subjects)
        for group, subjects in design.get("subjects_per_group", {}).items()
    }

    # NEW: Group display names mapping
    self.group_display_names = design.get("group_display_names", {}).copy()

    # Ensure all groups have display names (default to ID)
    for group in self.groups:
        if group not in self.group_display_names:
            self.group_display_names[group] = group

    # UI state
    self.selected_group_index = None
    self.selected_day_index = None

    super().__init__(parent, title="Editar Design Experimental")
```

**Modificar UI de grupos (linha ~86) - SUBSTITUIR seção de grupos por:**

```python
# Groups section
groups_frame = Frame(master)
groups_frame.pack(fill="both", expand=True, padx=10, pady=5)

Label(
    groups_frame,
    text="Grupos Experimentais:",
    font=("TkDefaultFont", 10, "bold")
).pack(anchor="w")

# Help text
Label(
    groups_frame,
    text="Configure o ID original e o nome descritivo para cada grupo",
    font=("TkDefaultFont", 8),
    foreground="gray"
).pack(anchor="w", pady=(0, 5))

# Groups table frame
groups_table_frame = Frame(groups_frame)
groups_table_frame.pack(fill="both", expand=True, pady=5)

# Headers
header_frame = Frame(groups_table_frame, relief="solid", borderwidth=1)
header_frame.pack(fill="x")

Label(
    header_frame,
    text="ID Original",
    width=15,
    font=("TkDefaultFont", 9, "bold"),
    relief="ridge"
).pack(side="left", fill="both", expand=True)

Label(
    header_frame,
    text="Nome para Exibição",
    width=25,
    font=("TkDefaultFont", 9, "bold"),
    relief="ridge"
).pack(side="left", fill="both", expand=True)

Label(
    header_frame,
    text="Ações",
    width=10,
    font=("TkDefaultFont", 9, "bold"),
    relief="ridge"
).pack(side="left")

# Scrollable content
groups_scroll_container = Frame(groups_table_frame)
groups_scroll_container.pack(fill="both", expand=True)

groups_canvas = Canvas(groups_scroll_container, height=150)
groups_scrollbar = Scrollbar(
    groups_scroll_container,
    orient="vertical",
    command=groups_canvas.yview
)
groups_canvas.configure(yscrollcommand=groups_scrollbar.set)

self.groups_rows_frame = Frame(groups_canvas)
groups_canvas.create_window((0, 0), window=self.groups_rows_frame, anchor="nw")

groups_canvas.pack(side="left", fill="both", expand=True)
groups_scrollbar.pack(side="right", fill="y")

# Bind scroll
self.groups_rows_frame.bind(
    "<Configure>",
    lambda e: groups_canvas.configure(scrollregion=groups_canvas.bbox("all"))
)

# Store UI elements for updates
self.group_id_labels = []
self.group_name_entries = []
self.group_name_vars = []

# Add group button
add_group_frame = Frame(groups_frame)
add_group_frame.pack(fill="x", pady=(5, 0))

Label(add_group_frame, text="Novo Grupo ID:").pack(side="left")
self.new_group_id_var = StringVar()
Entry(
    add_group_frame,
    textvariable=self.new_group_id_var,
    width=15
).pack(side="left", padx=5)

Label(add_group_frame, text="Nome:").pack(side="left")
self.new_group_name_var = StringVar()
Entry(
    add_group_frame,
    textvariable=self.new_group_name_var,
    width=20
).pack(side="left", padx=5)

Button(
    add_group_frame,
    text="➕ Adicionar Grupo",
    command=self._add_group
).pack(side="left", padx=5)

# Populate groups table
self._refresh_groups_table()
```

**Adicionar nova função `_refresh_groups_table()`:**

```python
def _refresh_groups_table(self):
    """Refresh the groups table with ID and display name."""

    # Clear existing rows
    for widget in self.groups_rows_frame.winfo_children():
        widget.destroy()

    self.group_id_labels = []
    self.group_name_entries = []
    self.group_name_vars = []

    # Create row for each group
    for i, group_id in enumerate(self.groups):
        row_frame = Frame(self.groups_rows_frame, relief="solid", borderwidth=1)
        row_frame.pack(fill="x")

        # ID label (read-only)
        id_label = Label(
            row_frame,
            text=group_id,
            width=15,
            anchor="w",
            relief="groove",
            bg="lightgray"
        )
        id_label.pack(side="left", fill="both", expand=True)
        self.group_id_labels.append(id_label)

        # Display name entry (editable)
        name_var = StringVar(value=self.group_display_names.get(group_id, group_id))
        name_entry = Entry(
            row_frame,
            textvariable=name_var,
            width=25,
            relief="groove"
        )
        name_entry.pack(side="left", fill="both", expand=True)
        self.group_name_vars.append(name_var)
        self.group_name_entries.append(name_entry)

        # Remove button
        remove_btn = Button(
            row_frame,
            text="🗑️",
            width=10,
            command=lambda idx=i: self._remove_group(idx)
        )
        remove_btn.pack(side="left")

    # Update canvas scroll region
    self.groups_rows_frame.update_idletasks()
```

**Modificar `_add_group()`:**

```python
def _add_group(self):
    """Add new group with ID and display name."""
    new_id = self.new_group_id_var.get().strip()
    new_name = self.new_group_name_var.get().strip()

    if not new_id:
        messagebox.showwarning(
            "ID Vazio",
            "Digite um ID para o novo grupo.",
            parent=self
        )
        return

    if new_id in self.groups:
        messagebox.showwarning(
            "ID Duplicado",
            f"O grupo '{new_id}' já existe.",
            parent=self
        )
        return

    self.groups.append(new_id)
    self.group_display_names[new_id] = new_name if new_name else new_id
    self.subjects_per_group[new_id] = []

    self.new_group_id_var.set("")
    self.new_group_name_var.set("")

    self._refresh_groups_table()
```

**Modificar `_remove_group()`:**

```python
def _remove_group(self, index):
    """Remove group at index."""
    if 0 <= index < len(self.groups):
        group_id = self.groups[index]

        confirm = messagebox.askyesno(
            "Confirmar Remoção",
            f"Remover grupo '{group_id}'?",
            parent=self
        )

        if confirm:
            self.groups.pop(index)
            self.group_display_names.pop(group_id, None)
            self.subjects_per_group.pop(group_id, None)
            self._refresh_groups_table()
```

**Modificar `apply()` para salvar display names:**

```python
def apply(self):
    """Apply changes (called when OK is clicked)."""

    # Update display names from entries
    for i, group_id in enumerate(self.groups):
        if i < len(self.group_name_vars):
            display_name = self.group_name_vars[i].get().strip()
            if display_name:
                self.group_display_names[group_id] = display_name
            else:
                # Fallback to ID if empty
                self.group_display_names[group_id] = group_id

    self.edited_design = {
        "groups": self.groups,
        "days": self.days,
        "subjects_per_group": self.subjects_per_group,
        "group_display_names": self.group_display_names,  # ← NOVO
        "pattern_used": self.input_design.get("pattern_used", "manual"),
        "confidence": self.input_design.get("confidence", 1.0),
    }

    log.info(
        "design_editor.saved",
        groups=len(self.groups),
        display_names=list(self.group_display_names.values())
    )
```

#### 3.2. Tornar Editor Obrigatório no Wizard

**Arquivo:** `src/zebtrack/ui/wizard/detection_step.py`

**Modificar `on_show()` linha ~180:**

```python
def on_show(self):
    """Called when step is shown - triggers design detection."""

    # ... código existente de detecção ...

    if success:
        # Auto-detect experimental design
        scanned_video_paths = [v["path"] for v in self.scanned_videos]
        self.detected_design = self._detect_design(scanned_video_paths)

        if self.detected_design:
            log.info(
                "wizard.design.detected",
                pattern=self.detected_design.get("pattern_used"),
                confidence=self.detected_design.get("confidence"),
            )

            # ✅ NOVO: Sempre abrir editor para confirmar/editar nomes
            self._open_design_editor_for_confirmation()
        else:
            # ... código de falha ...
```

**Adicionar nova função `_open_design_editor_for_confirmation()`:**

```python
def _open_design_editor_for_confirmation(self):
    """
    Abre editor de design automaticamente para usuário confirmar/editar.
    Diferente do botão manual, este é chamado automaticamente após detecção.
    """

    from zebtrack.ui.wizard.design_editor_dialog import DesignEditorDialog

    # Show info message first
    message = (
        "Design experimental detectado!\n\n"
        f"Grupos encontrados: {len(self.detected_design['groups'])}\n"
        f"Dias: {len(self.detected_design.get('days', []))}\n\n"
        "Na próxima tela, você pode:\n"
        "• Editar nomes dos grupos para facilitar identificação\n"
        "• Adicionar/remover grupos ou dias\n"
        "• Confirmar se está tudo correto"
    )

    from tkinter import messagebox
    messagebox.showinfo("Design Detectado", message, parent=self)

    # Open editor
    editor = DesignEditorDialog(self, self.detected_design)

    if editor.edited_design:
        self.detected_design = editor.edited_design
        self._update_design_summary()

        log.info(
            "wizard.design.edited_by_user",
            groups=len(self.detected_design["groups"]),
            has_display_names=bool(self.detected_design.get("group_display_names"))
        )
    else:
        # User cancelled - keep original detection
        log.info("wizard.design.editor_cancelled")
```

---

### ✅ Solução 4: Reorganizar Aba Relatórios com Hierarquia

**Arquivo:** `src/zebtrack/ui/gui.py`

**Modificar `_create_reports_tab()` linha ~2680:**

```python
def _create_reports_tab(self):
    """Creates the tab for viewing processed data and generating reports."""
    reports_tab_frame = ttk.Frame(self.notebook, padding="10")
    self.notebook.add(reports_tab_frame, text="Relatórios")

    # === Video List (Hierarchical) ===
    list_frame = ttk.LabelFrame(
        reports_tab_frame, text="Estrutura do Experimento", padding=10
    )
    list_frame.pack(fill="both", expand=True, pady=5)

    self.reports_tree = ttk.Treeview(
        list_frame,
        columns=("arena", "rois", "trajectory", "status"),
        show="tree headings"  # Hierárquico
    )

    # Headers
    self.reports_tree.heading("#0", text="Nome")
    self.reports_tree.heading("arena", text="🏛️ Arena")
    self.reports_tree.heading("rois", text="📍 ROIs")
    self.reports_tree.heading("trajectory", text="📈 Trajetória")
    self.reports_tree.heading("status", text="Status")

    # Column widths
    self.reports_tree.column("#0", width=300, stretch=True)
    self.reports_tree.column("arena", width=70, anchor="center")
    self.reports_tree.column("rois", width=70, anchor="center")
    self.reports_tree.column("trajectory", width=90, anchor="center")
    self.reports_tree.column("status", width=100)

    self.reports_tree.pack(side="left", fill="both", expand=True)

    scrollbar = ttk.Scrollbar(
        list_frame, orient="vertical", command=self.reports_tree.yview
    )
    self.reports_tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")

    self.reports_tree.bind("<<TreeviewSelect>>", self._on_report_item_select)

    # ... resto do código de botões permanece igual ...
```

**Modificar `update_reports_tree()` linha ~2726:**

```python
def update_reports_tree(self):
    """Populates the reports Treeview with hierarchical experimental structure."""

    # Clear existing
    for item in self.reports_tree.get_children():
        self.reports_tree.delete(item)

    if not self.controller.project_manager.project_path:
        return

    all_videos = self.controller.project_manager.get_all_videos()

    # Group by hierarchy: group > day > subject
    hierarchy = {}

    for video in all_videos:
        metadata = video.get("metadata", {})
        group_id = metadata.get("group", "Sem Grupo")
        group_display = metadata.get("group_display_name", group_id)
        day = metadata.get("day", "Sem Dia")
        subject = metadata.get("subject", "Desconhecido")

        # Build hierarchy
        if group_id not in hierarchy:
            hierarchy[group_id] = {
                "display": group_display,
                "days": {}
            }

        if day not in hierarchy[group_id]["days"]:
            hierarchy[group_id]["days"][day] = []

        hierarchy[group_id]["days"][day].append(video)

    # Populate tree
    for group_id in sorted(hierarchy.keys()):
        group_data = hierarchy[group_id]
        group_display = group_data["display"]

        # Count totals for group
        total_videos = sum(len(vids) for vids in group_data["days"].values())
        total_arena = sum(
            1 for day_vids in group_data["days"].values()
            for v in day_vids if v.get("has_arena")
        )
        total_rois = sum(
            1 for day_vids in group_data["days"].values()
            for v in day_vids if v.get("has_rois")
        )
        total_trajectory = sum(
            1 for day_vids in group_data["days"].values()
            for v in day_vids if v.get("has_trajectory")
        )

        # Insert group node
        group_node = self.reports_tree.insert(
            "",
            "end",
            text=f"🏷️ {group_display}",
            values=(
                f"{total_arena}/{total_videos}",
                f"{total_rois}/{total_videos}",
                f"{total_trajectory}/{total_videos}",
                f"{total_videos} vídeos"
            ),
            open=True
        )

        # Insert days
        for day in sorted(group_data["days"].keys()):
            videos = group_data["days"][day]

            day_arena = sum(1 for v in videos if v.get("has_arena"))
            day_rois = sum(1 for v in videos if v.get("has_rois"))
            day_trajectory = sum(1 for v in videos if v.get("has_trajectory"))

            day_node = self.reports_tree.insert(
                group_node,
                "end",
                text=f"📅 Dia {day}",
                values=(
                    f"{day_arena}/{len(videos)}",
                    f"{day_rois}/{len(videos)}",
                    f"{day_trajectory}/{len(videos)}",
                    f"{len(videos)} vídeos"
                ),
                open=False
            )

            # Insert videos
            for video in sorted(
                videos,
                key=lambda v: v.get("metadata", {}).get("subject", 0)
            ):
                subject = video["metadata"].get("subject", "?")
                filename = os.path.basename(video["path"])

                self.reports_tree.insert(
                    day_node,
                    "end",
                    text=f"🐟 Sujeito {subject:02d}  ({filename})",
                    values=(
                        "✓" if video.get("has_arena") else "✗",
                        "✓" if video.get("has_rois") else "✗",
                        "✓" if video.get("has_trajectory") else "✗",
                        video.get("status", "pending")
                    ),
                    tags=(video["path"],)  # Store for selection
                )

    log.info(
        "gui.reports_tree.updated",
        groups=len(hierarchy),
        total_videos=len(all_videos)
    )
```

---

### ✅ Solução 5: Mensagem de Orientação Pós-Criação

**Arquivo:** `src/zebtrack/core/controller.py`

**Adicionar após linha 390 em `create_project_workflow()`:**

```python
if self.setup_detector(temp_animal_method=animal_method):
    self.view._load_project_view()

    # ✅ NOVO: Mostrar guia de próximos passos
    if wizard_metadata:
        self._show_post_creation_guide(wizard_metadata)
```

**Adicionar nova função:**

```python
def _show_post_creation_guide(self, wizard_metadata: dict):
    """
    Mostra diálogo orientando próximos passos após criação do projeto.

    Personaliza mensagem baseado no que foi importado:
    - Zonas disponíveis → ver aba Configuração de Zonas
    - Trajetórias prontas → gerar relatórios
    - Vídeos pendentes → processar vídeos
    """

    import_config = wizard_metadata.get("import_config", [])

    if not import_config:
        # Projeto vazio, orientação genérica
        return

    # Analisa status dos vídeos
    total_videos = len(import_config)
    videos_with_arena = sum(1 for c in import_config if c.get("has_arena"))
    videos_with_rois = sum(1 for c in import_config if c.get("has_rois"))
    videos_with_trajectory = sum(1 for c in import_config if c.get("has_trajectory"))
    videos_pending = total_videos - videos_with_trajectory

    # Monta mensagem personalizada
    lines = []
    lines.append("🎉 Projeto criado com sucesso!")
    lines.append("")
    lines.append("📊 **Status dos Vídeos:**")
    lines.append(f"  • Total de vídeos: {total_videos}")
    lines.append(f"  • Com arena definida: {videos_with_arena}")
    lines.append(f"  • Com ROIs definidas: {videos_with_rois}")
    lines.append(f"  • Com trajetória completa: {videos_with_trajectory}")
    lines.append(f"  • Pendentes de processamento: {videos_pending}")
    lines.append("")
    lines.append("🚀 **Próximos Passos Recomendados:**")
    lines.append("")

    step_num = 1

    # Passo 1: Visualizar zonas (se houver)
    if videos_with_arena > 0 or videos_with_rois > 0:
        lines.append(f"{step_num}. **Visualizar e Ajustar Zonas Importadas**")
        lines.append("   ├─ Vá para a aba: **Configuração de Zonas**")
        lines.append("   ├─ No painel 'Selecionar Vídeo para Desenho':")
        lines.append("   │  • Escolha um vídeo da lista hierárquica")
        lines.append("   │  • Observe os símbolos 🟢/⚫ para ver status")
        lines.append("   │  • Clique duas vezes ou use o botão 'Carregar Frame'")
        lines.append("   └─ Verifique se as zonas estão corretas")
        lines.append("      (você pode editar clicando com botão direito)")
        lines.append("")
        step_num += 1

    # Passo 2: Processar pendentes (se houver)
    if videos_pending > 0:
        lines.append(f"{step_num}. **Processar Vídeos Pendentes** ({videos_pending} vídeos)")
        lines.append("   ├─ Vá para a aba: **Controle Principal**")
        lines.append("   ├─ Verifique os intervalos de processamento")
        lines.append("   └─ Clique em: 'Adicionar e Processar Novos Vídeos'")
        lines.append("")
        step_num += 1

    # Passo 3: Gerar relatórios (se houver dados completos)
    if videos_with_trajectory > 0:
        lines.append(f"{step_num}. **Gerar Relatórios** ({videos_with_trajectory} vídeos prontos)")
        lines.append("   ├─ Vá para a aba: **Relatórios**")
        lines.append("   ├─ Navegue pela estrutura hierárquica:")
        lines.append("   │  • 🏷️ Grupos → 📅 Dias → 🐟 Sujeitos")
        lines.append("   ├─ Selecione vídeos com status 'processed'")
        lines.append("   └─ Clique em:")
        lines.append("      • 'Gerar Relatório para Selecionados' (parcial)")
        lines.append("      • 'Gerar Relatório Unificado' (todos)")
        lines.append("")
        step_num += 1

    # Dicas extras
    lines.append("💡 **Dicas:**")
    lines.append("  • Use a busca 🔍 para filtrar vídeos rapidamente")
    lines.append("  • Os símbolos 🟢/⚫ indicam disponibilidade de dados")
    lines.append("  • Você pode ajustar zonas antes de processar")

    message = "\n".join(lines)

    self.view.show_info(
        "Bem-vindo ao Projeto!",
        message
    )

    log.info(
        "controller.post_creation_guide.shown",
        total_videos=total_videos,
        with_arena=videos_with_arena,
        with_trajectory=videos_with_trajectory,
        pending=videos_pending
    )
```

---

## RESUMO DE ARQUIVOS A MODIFICAR

1. **`src/zebtrack/ui/gui.py`** (PRINCIPAL - ~300 linhas)
   - `_create_zone_control_widgets()`: Adicionar seletor de vídeos
   - `_populate_video_selector_tree()`: NOVA (~60 linhas)
   - `_load_selected_video_frame()`: NOVA (~40 linhas)
   - `_on_video_tree_double_click()`: NOVA (~3 linhas)
   - `_filter_video_tree()`: NOVA (~10 linhas)
   - `_create_reports_tab()`: Modificar TreeView (~10 linhas modificadas)
   - `update_reports_tree()`: Reorganizar hierarquia (~80 linhas)
   - `_load_project_view()`: Chamar população do seletor (~1 linha)

2. **`src/zebtrack/core/project_manager.py`** (~30 linhas modificadas)
   - `add_video_batch()`: Adicionar metadados e flags

3. **`src/zebtrack/ui/wizard/design_editor_dialog.py`** (~150 linhas)
   - `__init__()`: Adicionar group_display_names (~5 linhas)
   - `body()`: Nova UI com tabela de grupos (~100 linhas substituídas)
   - `_refresh_groups_table()`: NOVA (~40 linhas)
   - `_add_group()`: Modificar (~15 linhas)
   - `_remove_group()`: Modificar (~10 linhas)
   - `apply()`: Salvar display names (~5 linhas modificadas)

4. **`src/zebtrack/ui/wizard/detection_step.py`** (~40 linhas)
   - `on_show()`: Tornar editor obrigatório (~5 linhas modificadas)
   - `_open_design_editor_for_confirmation()`: NOVA (~35 linhas)

5. **`src/zebtrack/ui/wizard/wizard_adapter.py`** (~60 linhas)
   - `enrich_videos_with_design_metadata()`: NOVA (~50 linhas)
   - `adapt_wizard_data()`: Chamar enrichment (~10 linhas modificadas)

6. **`src/zebtrack/core/controller.py`** (~80 linhas)
   - `create_project_workflow()`: Chamar guia pós-criação (~5 linhas)
   - `_show_post_creation_guide()`: NOVA (~75 linhas)

**Total Estimado:** ~650 linhas de código (adições + modificações)

---

## ORDEM DE IMPLEMENTAÇÃO

**Fase 1: Infraestrutura de Dados (30 min)**
1. ✅ Persistir metadados (`project_manager.py`)
2. ✅ Enriquecer vídeos (`wizard_adapter.py`)

**Fase 2: Editor de Design (1h)**
3. ✅ Melhorar editor de grupos (`design_editor_dialog.py`)
4. ✅ Tornar editor obrigatório (`detection_step.py`)

**Fase 3: Interface - Zonas (1h 30min)**
5. ✅ Seletor de vídeos (`gui.py` - aba zonas)
   - Adicionar widget
   - Implementar população
   - Implementar carregamento de frame

**Fase 4: Interface - Relatórios (45min)**
6. ✅ Reorganizar aba relatórios (`gui.py`)
   - Modificar TreeView
   - Implementar hierarquia

**Fase 5: UX - Orientação (30min)**
7. ✅ Mensagem de orientação (`controller.py`)

**Tempo Total Estimado:** ~4 horas

---

## TESTES NECESSÁRIOS

### Teste 1: Metadados Persistidos
- [ ] Criar projeto com design detectado
- [ ] Verificar `project.json`: campo `metadata` nos vídeos
- [ ] Verificar `group`, `group_display_name`, `day`, `subject`

### Teste 2: Editor de Grupos
- [ ] Wizard detecta design
- [ ] Editor abre automaticamente
- [ ] Editar nome de grupo: `Control` → `Veículo`
- [ ] Salvar e verificar no resumo
- [ ] Verificar no `project.json`

### Teste 3: Seletor de Vídeos
- [ ] Abrir projeto com vídeos
- [ ] Verificar hierarquia: Grupo > Dia > Sujeito
- [ ] Verificar símbolos 🟢⚫ corretos
- [ ] Selecionar vídeo e carregar frame
- [ ] Verificar zonas aparecem no canvas

### Teste 4: Aba Relatórios
- [ ] Abrir projeto
- [ ] Verificar hierarquia na TreeView
- [ ] Verificar colunas Arena/ROIs/Trajetória
- [ ] Verificar contadores (ex: "3/5")

### Teste 5: Mensagem de Orientação
- [ ] Criar projeto com vídeos importados
- [ ] Verificar mensagem personalizada aparece
- [ ] Verificar passos corretos baseado em status

---

## NOTAS IMPORTANTES

1. **Compatibilidade com projetos antigos:**
   - Projetos criados antes desta atualização não terão metadados
   - Adicionar fallback: re-extrair via regex se `metadata` ausente
   - Adicionar migração opcional em `load_project()`

2. **Performance:**
   - TreeView hierárquica pode ser lenta com >1000 vídeos
   - Considerar lazy loading para projetos grandes
   - Usar cache para hierarquia calculada

3. **i18n (Internacionalização):**
   - Emojis podem não aparecer em todos os sistemas
   - Ter fallback para símbolos ASCII: `[A]`, `[R]`, `[T]`

4. **Extensibilidade:**
   - Estrutura de metadados permite adicionar novos campos
   - Ex: `treatment_dose`, `timepoint`, `batch_number`

---

## PRÓXIMOS PASSOS (Pós-Implementação)

1. **Documentação:**
   - Atualizar `docs/ARCHITECTURE.md`
   - Adicionar screenshots no README
   - Criar guia de migração de projetos antigos

2. **Melhorias Futuras:**
   - Filtro avançado na TreeView (por status, grupo, dia)
   - Exportar estrutura hierárquica para CSV
   - Visualização de múltiplos frames lado a lado
   - Batch editing de metadados

3. **Otimizações:**
   - Cache de hierarquia calculada
   - Virtualização de TreeView para grandes datasets
   - Índice de vídeos para busca rápida

---

**FIM DO PLANO**
