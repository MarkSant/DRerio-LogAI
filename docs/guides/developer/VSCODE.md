# VS Code Configuration & Extensions

Workspace setup notes specific to DRerio LogAI. Moved out of `CLAUDE.md` on
2026-05-09 — the agent doesn't need to re-read this in every conversation.

## Required extensions

- **Python / Pylance** — use the Poetry venv interpreter; keep terminal and editor aligned.
- **Ruff** (`charliermarsh.ruff`) — the only Python formatter/linter; enable on-save fixes.
- **Mypy** (`matangover.mypy`) — daemon-based. Prefer `mypy.runUsingActiveInterpreter=true`;
  align with `mypy.ini`/`pyproject.toml`; use "Mypy: Restart Daemon and Recheck Workspace" if stale.
- **Python Debugger** — debug and manage envs using the same Poetry interpreter.
- **Jupyter** (Microsoft) — for notebook exploration and data analysis; kernel auto-selects Poetry venv.
- **PowerShell** — for scripts and automation.
- **GitLens** (`eamodio.gitlens`) — primary Git tool; replaces Git History.
- **GitHub Copilot / Copilot Chat / PRs / Actions** — follow repo instructions.
- **Error Lens** — inline error/warning display; errors and warnings only (not hints/info); CSpell excluded.
- **TODO Tree** — tracks TODO, FIXME, HACK, BUG, XXX, DEPRECATED tags; excludes build artifacts and archive folders.
- **YAML / markdownlint / Code Spell Checker** — keep lint rules on; fix warnings rather than disable.

### Authority matrix

- **Local commit graph / history**: GitLens.
- **PR linkage / base metadata**: GitHub Pull Requests extension.

## Removed extensions (DO NOT reinstall)

| Extension                       | Reason                                              |
| ------------------------------- | --------------------------------------------------- |
| `ms-python.mypy-type-checker`   | Duplicated diagnostics with `matangover.mypy`       |
| `ms-python.vscode-python-envs`  | Triggered WSL popups via `wsl.exe` stub             |
| `yzhang.markdown-all-in-one`    | Redundant with `davidanson.vscode-markdownlint`     |
| `donjayamanne.githistory`       | Replaced by `eamodio.gitlens`                       |
| `tomoki1207.pdf`                | Unused — no PDF workflows                           |
| `mechatroner.rainbow-csv`       | Unused — project uses Parquet, not CSV              |

## MCP server configuration

- **GitHub MCP** (`.vscode/mcp.json`): configured via
  `@modelcontextprotocol/server-github`. Enables agents to interact with issues,
  PRs, code search, and repository metadata directly from VS Code.
- **Root-level** (`.mcp.json`): same GitHub server config for agents using
  root-level MCP (e.g., Claude CLI). Requires `GITHUB_TOKEN` env var.
- **Requirement**: Node.js must be installed (for `npx`). A GitHub PAT with
  `repo` scope is needed.
- **Optional**: if `.mcp.json` is absent or MCP servers are unavailable,
  continue with local tools and GitHub extensions without blocking tasks.

## Workspace performance (OneDrive optimization)

- **`files.watcherExclude`** in `.vscode/settings.json` excludes:
  `openvino_model_cache/`, `htmlcov/`, `MagicMock/`, `live_analysis_sessions/`,
  `logs/`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.hypothesis/`,
  `.mypy_cache/`. **Critical** for reducing CPU/disk I/O on OneDrive-synced workspaces.
- **`search.exclude`** extended to also exclude: `htmlcov/`, `MagicMock/`,
  `live_analysis_sessions/`, `logs/`, `.ruff_cache/`, `.pytest_cache/`,
  `.hypothesis/` from global search.
- **Deprecated settings removed** (Mar 2026): `python.linting.*`,
  `python.formatting.provider`, `python-envs.defaultEnvManager` — all
  deprecated by the Python extension. Ruff handles all formatting/linting.

## Recommended settings

```jsonc
{
  // Interpreter & terminal
  "python.defaultInterpreterPath": "<poetry venv path>",
  "terminal.integrated.defaultProfile.windows": "PowerShell",

  // Pylance
  "python.analysis.typeCheckingMode": "basic",

  // Ruff as formatter
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },

  // Mypy daemon
  "mypy.runUsingActiveInterpreter": true
}
```

Use **"Python: Select Interpreter"** to pick the Poetry venv; keep terminals aligned.
Use **"Mypy: Restart Daemon and Recheck Workspace"** when type errors look stale.

## Tooling checklist

- [ ] Active Python interpreter is the Poetry venv used by `poetry run`.
- [ ] Ruff is the only Python formatter (disable Black/Pylint/Flake8 formatters).
- [ ] Mypy config is centralized (mypy.ini/pyproject) and editor uses the same config.
- [ ] Only `matangover.mypy` installed (NOT `ms-python.mypy-type-checker`).
- [ ] YAML/Markdown linters are enabled for config/docs quality.
- [ ] Error Lens shows errors/warnings only (not hints/info); CSpell excluded.
- [ ] TODO Tree excludes build artifacts and archive folders.
