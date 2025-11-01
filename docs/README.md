# ZebTrack-AI Documentation

Welcome to the ZebTrack-AI (DRerio LogAI) documentation repository.

## Documentation Structure

### 📚 [API Reference](api/)
Complete API documentation generated with Sphinx.

**What's inside:**
- Auto-generated documentation from source code
- Type hints and docstrings
- Module hierarchy and relationships
- Links to source code

**Quick Start:**
```bash
# Build HTML documentation
sphinx-build -b html docs/api/source docs/api/build/html

# View documentation
open docs/api/build/html/index.html
```

See [api/README.md](api/README.md) for detailed instructions.

---

### 🔄 [Migration Guides](migration/)
Step-by-step guides for upgrading between major versions.

**Available Guides:**
- [v2.1 → v3.0](migration/v2.1-to-v3.0.md) - Main migration guide
- [Reporter v3.0 Migration](migration/reporter-v3-migration.md) - Detailed guide

**Automated Tools:**
- [Migration Script](../scripts/migrate_reporter_v3.py) - Automated code migration

**Quick Start:**
```bash
# Preview migration changes
python scripts/migrate_reporter_v3.py --dry-run

# Apply migrations
python scripts/migrate_reporter_v3.py --apply
```

See [migration/README.md](migration/README.md) for more information.

---

### 📖 Architecture & Guides

Existing documentation in this directory:

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture overview
- **[REFERENCE_GUIDE.md](REFERENCE_GUIDE.md)** - Developer reference
- **[DEPENDENCY_INJECTION_GUIDE.md](DEPENDENCY_INJECTION_GUIDE.md)** - DI patterns
- **[STATE_MANAGEMENT_GUIDE.md](STATE_MANAGEMENT_GUIDE.md)** - State management
- **[SERVICE_LAYER_PATTERNS.md](SERVICE_LAYER_PATTERNS.md)** - Service patterns
- **[BEHAVIORAL_METRICS.md](BEHAVIORAL_METRICS.md)** - Metrics documentation
- **[COORDINATE_SYSTEMS.md](COORDINATE_SYSTEMS.md)** - Coordinate systems
- **[DEVELOPER_GUIDE_WIZARD.md](DEVELOPER_GUIDE_WIZARD.md)** - Wizard development
- **[ERROR_HANDLING.md](ERROR_HANDLING.md)** - Error handling patterns
- **[PERFORMANCE_TUNING.md](PERFORMANCE_TUNING.md)** - Performance guide
- **[TESTING_TKINTER_WINDOWS.md](TESTING_TKINTER_WINDOWS.md)** - UI testing
- **[WIDGETS.md](WIDGETS.md)** - Widget documentation
- **[WORKFLOWS.md](WORKFLOWS.md)** - Development workflows

---

## Quick Links

### For Developers
- 🏗️ [Architecture Overview](ARCHITECTURE.md)
- 🔧 [Developer Reference](REFERENCE_GUIDE.md)
- 🧪 [Testing Guide](TESTING_TKINTER_WINDOWS.md)
- 📊 [Performance Tuning](PERFORMANCE_TUNING.md)

### For Users
- 📚 [API Documentation](api/build/html/index.html) (after building)
- 🔄 [Migration Guides](migration/)
- 📝 [Known Issues](KNOWN_ISSUES.md)

### For Contributors
- 🔄 [Workflows](WORKFLOWS.md)
- 🎨 [Widgets](WIDGETS.md)
- 🧩 [Service Patterns](SERVICE_LAYER_PATTERNS.md)
- ⚠️ [Error Handling](ERROR_HANDLING.md)

---

## Building Documentation

### API Documentation

Prerequisites:
```bash
pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints myst-parser
```

Build:
```bash
sphinx-build -b html docs/api/source docs/api/build/html
```

### ReadTheDocs

The API documentation is configured for automatic builds on ReadTheDocs via the `.readthedocs.yml` file in the repository root.

---

## Contributing to Documentation

### Adding New API Documentation

1. Create a new RST file in `docs/api/source/modules/`
2. Add the file to the appropriate `toctree` in `docs/api/source/index.rst`
3. Build and verify: `sphinx-build -b html docs/api/source docs/api/build/html`

### Creating Migration Guides

1. Create a new markdown file in `docs/migration/`
2. Follow the existing format (see [reporter-v3-migration.md](migration/reporter-v3-migration.md))
3. Include:
   - Background and rationale
   - Before/after code examples
   - Migration steps
   - Troubleshooting
4. Update the [migration README](migration/README.md)

### Updating Existing Docs

1. Make changes to the appropriate markdown file
2. Ensure links are updated
3. Test any code examples
4. Update the changelog if applicable

---

## Documentation Standards

- **Language:** Brazilian Portuguese (pt_BR) for API docs, English for technical guides
- **Format:** Markdown for guides, RST for Sphinx documentation
- **Code Examples:** Include both "before" and "after" examples when showing changes
- **Links:** Use relative links within the repository
- **Images:** Store in `docs/wiki/` or appropriate subdirectory

---

## Support

For questions or issues with the documentation:

1. Check the [Issue Tracker](https://github.com/MarkSant/ZebTrack-AI/issues)
2. Review existing documentation
3. Open a new issue with label `documentation`

---

## License

This documentation is part of the ZebTrack-AI project and is licensed under the MIT License.
