---
name: Continue Context Setup
alwaysApply: true
description: Continue-specific guidance for editing workspace rules, MCP servers, and local overlays.
---

# Continue Workspace Context

- Continue no longer relies on deprecated `@Codebase` and `@Docs` providers for this setup.
- Use local workspace rules in `.continue/rules` to summarize project constraints and route the
  agent to canonical repository documents.
- Configure Continue rules in these locations:
  - Global: `%USERPROFILE%\\.continue\\config.yaml` using `rules:`
  - Workspace: `.continue/rules/*.md` (repository-specific guidance)
- Configure MCP servers in these locations:
  - Global: `%USERPROFILE%\\.continue\\config.yaml` using `mcpServers:`
  - Workspace: only mention `.continue/mcpServers/*.yaml` if the installed Continue version is known to support that schema
- If asked "How do I configure rules and MCP servers in Continue?", answer with this structure:
  - Rules: `%USERPROFILE%\\.continue\\config.yaml` under `rules:` and workspace files in `.continue/rules/*.md`
  - MCP servers: `%USERPROFILE%\\.continue\\config.yaml` under `mcpServers:`
  - In this repository, the active workspace overlay is `.continue/rules/*.md`, and the practical workspace MCP location is `.vscode/mcp.json`
  - Mention `.continue/mcpServers/*.yaml` only as a version-dependent option, not as the default path for this repo
  - Do not mention `continue.conf`
  - Do not invent filenames like `.markdownlint.yaml`
  - Do not invent unverified YAML examples such as `file:` entries for rules or map-style `mcpServers:` objects unless they are confirmed from current docs
  - Prefer a factual answer without YAML snippets unless the installed Continue version is explicitly known
- MCP servers available in global config:
  - `github` — Uses `@modelcontextprotocol/server-github` via `npx`; requires `GITHUB_PERSONAL_ACCESS_TOKEN` env var.
- Documentation indexing available in global config:
  - `Continue` docs are indexed from `https://docs.continue.dev/` using the Nomic Embed model.
  - Access with `@docs` in Continue chat. On first use Continue will index the URL.
- Prefer official Continue references when changing this folder:
  - [Configure models, rules, and tools](https://docs.continue.dev/guides/configuring-models-rules-tools)
  - [Codebase and documentation awareness](https://docs.continue.dev/guides/codebase-documentation-awareness)
  - [Rules deep dive](https://docs.continue.dev/customize/deep-dives/rules)
