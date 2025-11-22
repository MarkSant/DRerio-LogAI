"""Testes para ApplicationBootstrapper.

Testes unitários para o serviço de bootstrap da aplicação.
Após refatoração significativa, a maioria dos testes internos foram removidos.
A funcionalidade é testada através de testes de integração.
"""

import pytest

from zebtrack.core.application_bootstrapper import ApplicationBootstrapper
from zebtrack.core.dependency_container import MainViewModelDependencies
from unittest.mock import MagicMock


@pytest.fixture
def mock_dependencies():
    """Cria dependências mockadas para testes."""
    deps = MagicMock(spec=MainViewModelDependencies)
    deps.state_manager = MagicMock()
    deps.settings_obj = MagicMock()
    return deps


class TestApplicationBootstrapperInitialization:
    """Testes de inicialização do bootstrapper."""

    def test_init_stores_dependencies(self, mock_dependencies):
        """Testa que dependências são armazenadas corretamente."""
        bootstrapper = ApplicationBootstrapper(mock_dependencies)

        assert bootstrapper.deps is mock_dependencies
        assert bootstrapper.state_manager is mock_dependencies.state_manager
        assert bootstrapper.settings is mock_dependencies.settings_obj
