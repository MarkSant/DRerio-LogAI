---
name: ZebTrack Guardrails
alwaysApply: true
description: Critical DRerio LogAI implementation constraints that the agent must preserve.
---

# DRerio LogAI Guardrails

- Run impact analysis before code changes with `python scripts/impact_analyzer.py`.
- Never import singleton settings with `from zebtrack import settings`; use constructor
  injection via `settings_obj`.
- Use `EventBusV2` for UI and event coordination. Do not reintroduce EventBus v1 patterns.
- Any UI update from non-main threads must be scheduled with `root.after(0, ...)`.
- For multi-aquarium flows, prefer `get_multi_aquarium_zone_data()` over `get_zone_data()`.
- Keep recorder schema assumptions intact; do not casually change Parquet columns or order.
