# Continue Workspace Setup

## Overview

This guide explains the Continue workspace overlay for ZebTrack-AI after deprecation of `@Codebase` and `@Docs` context providers.

**Current Status**: Workspace rules and global config are active. For this repository, the stable workspace overlay is `.continue/rules/`, and workspace MCP integration is handled through `.vscode/mcp.json`.

## Architecture

Split configuration model:

- **Global** (`%USERPROFILE%\.continue\config.yaml`): Models, rules, MCP servers, and defaults
- **Workspace** (`.continue/rules/`, `.vscode/mcp.json`): Repository-specific constraints and VS Code MCP integration
- **Secrets**: Environment variables (inherited by Continue + VS Code)

## Phase 1: Workspace Overlay (✅ Complete)

Workspace rules summarize non-negotiable constraints and point to canonical files:

- `.continue/rules/01-zebtrack-architecture.md` — Composition root, key files
- `.continue/rules/02-zebtrack-guardrails.md` — DI, EventBusV2, UI threading
- `.continue/rules/03-zebtrack-workflow.md` — Poetry, docs, testing
- `.continue/rules/04-continue-context.md` — Continue-specific guidance

**Canonical Source Files** (referenced by rules, not duplicated):

- `AGENTS.md` (primary agent guidance)
- `.copilot-context.yaml` (navigation index)
- `.copilot-impact-map.yaml` (dependency graphs)
- `docs/explanation/architecture.md` (system design)
- `docs/guides/developer/impact_analysis.md` (impact analysis protocol)
- `docs/tasks/active/ROLLING_TASK_LOG.md` (active work log)

## Phase 2: Global Configuration (✅ Complete)

### Model Setup

Global config at `%USERPROFILE%\.continue\config.yaml` includes the active local model assignments and any global `rules:` or `mcpServers:` entries you want Continue to load across projects.

**Active local model roles**:

- `Qwen 3.5 9B Local` — `chat`, `edit`, `apply`
- `Qwen 3.5 4B Autocomplete` — `autocomplete`
- `Nomic Embed` — `embed`

This keeps the setup offline-first and aligned with the models actually installed in Ollama.

### Global Rules and MCP Servers

- Put project-agnostic Continue rules in `%USERPROFILE%\.continue\config.yaml` under `rules:`.
- Put global Continue MCP servers in `%USERPROFILE%\.continue\config.yaml` under `mcpServers:`.
- For ZebTrack-AI, prefer `.continue/rules/*.md` for repository guidance and `.vscode/mcp.json` for workspace MCP integration used from VS Code.
- Only use workspace `.continue/mcpServers/*.yaml` if you have confirmed that your installed Continue version supports that schema.

### Secret Handling (Security Fix - Phase 2)

Hardcoded API keys **removed** from global config. Now uses environment variables:

| Variable | Service | Set via |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude (Anthropic) | Process env or `~/.continue/.env` |
| `GOOGLE_GENAI_API_KEY` | Gemini | Process env or `~/.continue/.env` |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub MCP | Process env (inherited by VS Code) |

**Windows Setup**:

```powershell
$env:ANTHROPIC_API_KEY = "<your-key>"
$env:GITHUB_PERSONAL_ACCESS_TOKEN = "<your-token>"
code "c:\Users\santa\OneDrive\UNESP\Pesquisa Canabidiol\Codigos_Programas\ZebTrack-AI"
```

**Alternative (Continue-local secrets)**:

Keep secrets in either:

- `%USERPROFILE%\.continue\.env`
- `<workspace>\.continue\.env`
- `<workspace>\.env`

**Note**: `.vscode/mcp.json` no longer stores GitHub token; expects `GITHUB_PERSONAL_ACCESS_TOKEN` in parent process environment.

### Workspace Context Awareness

Continue automatically loads:

- Workspace rules from `.continue/rules/**/*.md`
- Global configuration from `%USERPROFILE%\.continue\config.yaml`

For this repository, treat `.continue/rules/` as the active workspace overlay. Do not assume workspace `.continue/mcpServers/**/*.yaml` is available unless it has been validated against the installed Continue version.

### Custom Commands

No custom Continue command files are required for the current working setup.

## Phase 3: Validation (Next Steps)

Reload Continue and use these prompts to verify configuration:

1. **Where is the ZebTrack composition root and which file wires dependency injection?**
   - Expected: `src/zebtrack/__main__.py` (entry) and `src/zebtrack/core/application_bootstrapper.py` (DI wiring)

2. **What is the safe accessor for multi-aquarium zone data in this repository?**
   - Expected: `ProjectManager.get_multi_aquarium_zone_data()` (not `get_zone_data()`)

3. **Before editing code in ZebTrack-AI, which impact analysis workflow should I follow?**
   - Expected: `python scripts/impact_analyzer.py <type> <name>` as documented in `docs/guides/developer/impact_analysis.md`

4. **What file tracks the active work log for this repository?**
   - Expected: `docs/tasks/active/ROLLING_TASK_LOG.md`

5. **How do I configure rules and MCP servers in Continue?**
   - Expected: Global `config.yaml` for `rules:` and `mcpServers:`, workspace `.continue/rules/*.md`, and `.vscode/mcp.json` as the practical workspace MCP location for this repo

## Files Modified (Phase 2)

- ✅ `%USERPROFILE%\.continue\config.yaml` — Removed hardcoded keys and normalized active local model roles
- ✅ `docs/guides/developer/continue_workspace_setup.md` — This file (Phase 2 documentation)
- ✅ `docs/tasks/active/ROLLING_TASK_LOG.md` — TASK-059 Phase 2 updates

## Troubleshooting

### Models not available

- Ensure Ollama is running: `ollama serve`
- Verify models: `ollama list`

### Cloud fallback failing

- Check environment variables: `$env:ANTHROPIC_API_KEY`
- Verify API keys in `~/.continue/.env` or process environment

### Workspace rules not loading

- Rules should appear in Chat after reload (View → Command Palette → "Continue: Reload")
- Check `.continue/rules/` folder exists in workspace

### Continue answer still hallucinates config paths or schema

- Reload Continue after editing `.continue/rules/04-continue-context.md`
- Re-test validation prompt #5
- If the answer still invents YAML structure, prefer a shorter factual answer with paths only and no config snippet

## References

- **Continue Docs**: [https://docs.continue.dev/guides/configuring-models-rules-tools](https://docs.continue.dev/guides/configuring-models-rules-tools)
- **Model Configuration**: [https://docs.continue.dev/customize/models](https://docs.continue.dev/customize/models)
- **Rules Documentation**: [https://docs.continue.dev/customize/deep-dives/rules](https://docs.continue.dev/customize/deep-dives/rules)
- **MCP Integration**: [https://docs.continue.dev/customize/deep-dives/model-context-protocol](https://docs.continue.dev/customize/deep-dives/model-context-protocol)

## Next Steps (Phase 4 - Optional)

If workspace rules + MCP documentation prove insufficient:

- Implement custom code RAG using LanceDB + Voyage AI embeddings (see Continue docs)
- Index high-value files: impact_analysis.md, AGENTS.md, .copilot-impact-map.yaml
- Enable `codebaseRetrieval` in Continue config
