# Migration Guides

This directory contains migration guides for upgrading between major versions of ZebTrack-AI.

## Available Guides

### [v2.1 → v3.0](v2.1-to-v3.0.md)

**Status:** Pre-release (November 2025)  
**Release Date:** February 2026

Main migration guide covering all breaking changes in v3.0:

- Reporter constructor removal (HIGH IMPACT)
- Settings singleton removal (MEDIUM IMPACT - already migrated)
- EventBus API changes (LOW IMPACT)

### [Reporter v3.0 Migration](reporter-v3-migration.md)

**Type:** Detailed guide

In-depth guide for migrating from the old Reporter constructor to the new `Reporter.from_analysis()` pattern. Includes:

- Background and rationale
- Before/after code examples
- Migration scenarios (unit tests, production code, custom analysis)
- Automated migration script usage
- Performance comparisons
- Troubleshooting

## Migration Tools

### Automated Migration Script

Location: `scripts/migrate_reporter_v3.py`

Automatically migrates Reporter instantiations from v2.1 to v3.0 pattern.

**Usage:**

```bash
# Preview changes (dry-run)
poetry run python scripts/migrate_reporter_v3.py --dry-run

# Apply changes to all test files
poetry run python scripts/migrate_reporter_v3.py --apply

# Migrate specific files
poetry run python scripts/migrate_reporter_v3.py tests/analysis/test_reporter.py --apply
```

**What it does:**

1. Identifies direct `Reporter(trajectory_df=...)` instantiations
2. Extracts constructor parameters
3. Generates equivalent code using `AnalysisService` + `Reporter.from_analysis()`
4. Preserves comments and code structure

**Limitations:**

- Cannot migrate highly dynamic code (e.g., `Reporter(**kwargs)`)
- Cannot migrate tests with complex mocks
- Manual review recommended after migration

## Migration Checklist

When upgrading to v3.0:

- [ ] Read the main migration guide ([v2.1-to-v3.0.md](v2.1-to-v3.0.md))
- [ ] Read the detailed Reporter guide ([reporter-v3-migration.md](reporter-v3-migration.md))
- [ ] Run migration script in dry-run mode
- [ ] Review suggested changes
- [ ] Apply migrations
- [ ] Run full test suite: `poetry run pytest`
- [ ] Check for deprecation warnings: `poetry run pytest -W error::DeprecationWarning`
- [ ] Test application end-to-end
- [ ] Update custom code if applicable

## Support

If you encounter issues during migration:

1. Check the [Issue Tracker](https://github.com/MarkSant/ZebTrack-AI/issues)
2. Review the troubleshooting sections in the migration guides
3. Open a new issue with label `migration-v3`

## Contributing

When creating new migration guides:

1. Follow the existing structure and format
2. Include clear before/after code examples
3. Explain the rationale for changes
4. Provide troubleshooting tips
5. Include performance comparisons if applicable
6. Create automated migration tools when possible
