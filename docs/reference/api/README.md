# API Documentation (Sphinx)

This guide describes how to build the API documentation for ZebTrack-AI using Sphinx.

## Current Status

The Sphinx source tree is maintained historically in docs/archive/api_sphinx/. Use it as the reference source when you need to regenerate or reintroduce API docs.

## Build Steps

1. Ensure dev dependencies are installed:
   - poetry install --with dev
2. Copy or sync Sphinx sources into an active location (recommended: docs/api/):
   - Copy docs/archive/api_sphinx/ to docs/api/
3. Build the HTML documentation:
   - sphinx-build -b html docs/api/source docs/api/build/html
4. Open docs/api/build/html/index.html in a browser.

## Notes

- The Sphinx toolchain is declared in pyproject.toml (sphinx, sphinx-rtd-theme, sphinx-autodoc-typehints).
- Network warnings from intersphinx are expected in restricted environments.
- If you reintroduce docs/api/ into active docs, update docs/INDEX.md if paths change.
