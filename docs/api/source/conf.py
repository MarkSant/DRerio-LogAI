"""Configuração Sphinx para ZebTrack-AI."""

import os
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

# -- Project information -----------------------------------------------------
project = 'ZebTrack-AI'
copyright = '2025, The Project Developers'
author = 'The Project Developers'
release = '0.1.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',           # Auto-geração de docs
    'sphinx.ext.napoleon',          # Suporte Google/NumPy docstrings
    'sphinx.ext.viewcode',          # Links para código-fonte
    'sphinx.ext.intersphinx',       # Links para docs externas
    'sphinx_autodoc_typehints',     # Type hints em docs
    'myst_parser',                  # Suporte Markdown
]

templates_path = ['_templates']
exclude_patterns = []

language = 'pt_BR'

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# -- Extension configuration -------------------------------------------------
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# Napoleon settings (Google/NumPy docstring style)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
}

# Type hints
autodoc_typehints = 'description'
autodoc_typehints_description_target = 'documented'
