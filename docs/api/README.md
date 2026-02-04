# ZebTrack-AI API Documentation

This directory contains the Sphinx-based API documentation for ZebTrack-AI (DRerio LogAI).

## Building the Documentation

### Prerequisites

Install the required dependencies:

```bash
poetry install --with dev
```

Or install Sphinx manually:

```bash
pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints myst-parser
```

### Build HTML Documentation

From the repository root:

```bash
# Build HTML documentation
sphinx-build -b html docs/api/source docs/api/build/html

# Build with strict warnings (fail on warnings)
sphinx-build -b html -W docs/api/source docs/api/build/html

# Check for broken links
sphinx-build -b linkcheck docs/api/source docs/api/build/linkcheck
```

### View Documentation

After building, open the generated HTML:

```bash
# Linux/Mac
open docs/api/build/html/index.html

# Windows
start docs/api/build/html/index.html
```

## Structure

```text
docs/api/
├── source/                 # Source RST files
│   ├── conf.py            # Sphinx configuration
│   ├── index.rst          # Main index
│   ├── _static/           # Static assets
│   ├── _templates/        # Custom templates
│   └── modules/           # Module documentation
│       ├── core/          # Core modules
│       ├── analysis/      # Analysis modules
│       ├── io/            # I/O modules
│       ├── ui/            # UI modules
│       └── plugins/       # Plugin modules
├── build/                 # Generated documentation (gitignored)
└── README.md             # This file
```

## ReadTheDocs Integration

This documentation is configured to be built automatically on ReadTheDocs via the `.readthedocs.yml` file in the repository root.

## Customization

### Theme

The documentation uses the [Read the Docs theme](https://sphinx-rtd-theme.readthedocs.io/). To customize:

1. Edit `docs/api/source/conf.py`
2. Modify `html_theme` and related options
3. Add custom CSS in `docs/api/source/_static/`

### Extensions

Current extensions:

- `sphinx.ext.autodoc` - Auto-generate documentation from docstrings
- `sphinx.ext.napoleon` - Support Google/NumPy docstring styles
- `sphinx.ext.viewcode` - Add links to source code
- `sphinx.ext.intersphinx` - Link to external documentation
- `sphinx_autodoc_typehints` - Include type hints in documentation
- `myst_parser` - Support Markdown in RST files

## Troubleshooting

### Missing Module Errors

If you see import errors during build:

```bash
# Ensure the package is importable
export PYTHONPATH=/path/to/ZebTrack-AI/src:$PYTHONPATH
```

### Warnings about Intersphinx

Network warnings are normal in sandboxed environments. They don't affect the build.

### Portuguese Language

The documentation is configured for Brazilian Portuguese (`pt_BR`). To change:

1. Edit `docs/api/source/conf.py`
2. Modify the `language` setting

## Contributing

When adding new modules:

1. Create a new RST file in the appropriate `modules/` subdirectory
2. Add the file to the appropriate `toctree` in `docs/api/source/index.rst`
3. Follow the existing patterns for autoclass/automodule directives
4. Build and verify the documentation
