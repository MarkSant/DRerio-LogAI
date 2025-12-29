# Full Tutorial: From Video to Results

This tutorial walks through the complete ZebTrack-AI workflow: creating a project with the wizard, configuring arenas/ROIs, running detections, and generating reports.

---

## Step 1 · Launch the wizard

1. Open a terminal in the project root and run `poetry run zebtrack`.
2. Click **"Create Project"**. The 5-step wizard (v1.7) opens automatically.
3. Follow the discovery step:
   - Choose **Experimental**, **Exploratory**, or **Live** mode.
   - Tell the wizard whether you want to reuse existing Parquet files (arena/ROIs/trajectory).
4. In step 2, add videos or folders. The preview tree summarizes the detected structure.
5. Step 3 analyses the folder structure and proposes groups/days/subjects. Adjust the regex live if something looks off.
6. Step 4 (Import Configuration) lets you decide per video what to do:
   - `SKIP` when all Parquets are present.
   - `IMPORT_ZONES` to reuse arena/ROIs but regenerate trajectories.
   - `PARTIAL` to reuse only the arena.
   - `FULL` when nothing should be imported.
7. Step 5 shows a consolidated summary (design detected, processing plan, expected run time). Click **Create Project** to persist it.

> 📘 Need extra details? See `docs/WIZARD_USER_GUIDE.md` for screenshots of every step.

---

## Step 2 · Configure arenas and ROIs

1. Go to the **"Configuração de Zonas"** tab.
2. Use **Detectar Aquário (Auto)** or draw the main arena manually.
3. Apply previously saved templates with the **Templates salvos** combobox. Use **📂 Importar e Aplicar Arquivo...** to load templates directly from JSON files.
4. Draw or edit ROIs. The editor now clamps vertices to the arena boundary and highlights clamped points (orange handles with extra circles), ensuring valid polygons.
5. Save the current layout as a template with **💾 Salvar Zonas Atuais** so that future projects can reuse them.

> 🛈 When editing ROIs, the cyan snapping indicator and the handles stay within the arena boundaries, preventing accidental drags outside the valid area.

---

## Step 3 · Tune detector settings

1. Open the **Configuração Avançada** tab to review `config.local.yaml` in-app. The editor validates values in real time using the Pydantic schema.
2. Configure detector thresholds (confidence/NMS), choose between YOLO and OpenVINO weights, and enable optional features like the UI event queue or Arduino integration.
3. Switch back to the main tab and pick the detector plugin you want to run.

---

## Step 4 · Process videos (or record new ones)

### Pre-recorded projects

1. In **Main Control**, click **"Adicionar e Processar Novos Vídeos/Pastas"**.
2. Confirm the wizard’s processing plan. ZebTrack-AI handles detection → tracking → analysis automatically.
3. The overlay view displays:
   - Current frame with bounding boxes.
   - Processing statistics (total frames, processed frames, detected frames, ETA).
   - The active tracking mode (multi-animal vs. single subject). The track selector locks automatically when the controller forces single-subject mode (e.g., during calibration).

### Live projects

1. Use the **Progresso do Experimento** grid to select the subject/day.
2. Configure countdowns or fixed durations if desired.
3. Start the session from **Main Control**. Video recording and analysis happen in one pass.

---

## Step 5 · Review results and export reports

1. Open the **Relatórios** tab once processing finishes.
2. Select specific videos or use **Gerar Relatório Unificado (Todos)** for an aggregated summary.
3. Choose the export format:
   - Excel (`.xlsx`) tidy tables.
   - CSV (`.csv`) for interoperability.
   - Parquet (`.parquet`) for analysis in pandas/R.
   - Word (`.docx`) document with plots, ROI maps, and an event appendix (enter/exit log).
4. Each processed video also receives a `<video>_results/` folder containing raw Parquets (`1_`, `2_`, `3_`), diagnostic MP4 (optional), and Excel/Word outputs.

### Report Metrics (v3.2+)

Reports now include enhanced velocity and geotaxis metrics:

| Metric | Description |
| --- | --- |
| **Mean Speed (cm/s)** | Average swimming velocity |
| **Max Speed (cm/s)** | Maximum instantaneous velocity |
| **Median Speed (cm/s)** | Median velocity (robust to outliers) |
| **Geotaxis Zona 1 - Fundo (%)** | Time spent in bottom zone |
| **Geotaxis Zona 2 (%)** | Time spent in middle zone |

> 📝 **Note**: Column names in Word reports now display with proper units (e.g., "Max Speed (cm/s)" instead of "Max Speed Cm S").

### Unified Reports Enhancements (v3.3)

The unified report has been robustly improved:

- **Identification & Metadata**: Uses the current project structure (Day/Group/Subject) to populate columns, automatically fixing "Unknown" or stale metadata from old files.
- **De-duplication**: Duplicate "Group" columns (e.g. `group` vs `group_id`) are automatically resolved to a single standard 'Group'.
- **Readable Colors**: ROI Colors are displayed as human-readable names (e.g. "Red", "Dark Blue") in Excel, replacing raw RGB tuples.
- **Report Management**: A new **"🗑️ Apagar Relatórios Unificados"** button allows you to safely clear old aggregated reports. The system now automatically handles OneDrive sync locks and read-only files during deletion.

---

## Step 6 · Tips and QA

- Run `poetry run pytest -q` and `poetry run ruff check .` before sharing results.
- Use `tests/manual/wizard_release_check.py` to validate new templates and translations.
- Keep `config.local.yaml` under version control (if it contains shared lab defaults) or document overrides in your project README.
- Consult `docs/REFERENCE_GUIDE.md` for formulas, ROI metrics, Arduino integration, and troubleshooting checklists.

You’re now ready to perform end-to-end experiments with ZebTrack-AI!
