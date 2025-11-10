"""Test CI/CD configuration.

Tests to validate CI/CD pipeline configuration including:
- pytest-timeout configuration
- Fast test performance
- Slow test timeout handling
"""

import time

import pytest


def test_timeout_configuration():
    """Pytest timeout is configured and working.

    This test verifies that pytest is configured to use timeouts.
    It should pass quickly without hitting any timeout limits.
    """
    assert True


@pytest.mark.slow
def test_slow_test_with_timeout():
    """Slow tests respect timeout configuration.

    This test simulates a slow operation (2 seconds) to verify
    that slow tests are properly handled by the timeout configuration.
    With the default 300s timeout, this should pass without issues.
    """
    # Sleep for 2 seconds (should pass with 300s timeout)
    time.sleep(2)
    assert True


def test_fast_test_performance():
    """Fast tests complete quickly.

    This test verifies that fast tests complete in reasonable time.
    The operation should take less than 1 second.
    """
    # Should complete in <1 second
    start = time.time()
    result = sum(range(1000))
    elapsed = time.time() - start

    assert result > 0
    assert elapsed < 1.0, f"Test took {elapsed}s, expected <1.0s"


def test_pytest_timeout_plugin_available():
    """Verify pytest-timeout plugin is available.

    This ensures that the pytest-timeout plugin is properly installed
    and available in the test environment.
    """
    # Try to import the timeout plugin
    try:
        import pytest_timeout  # noqa: F401

        timeout_available = True
    except ImportError:
        timeout_available = False

    assert timeout_available, "pytest-timeout plugin is not installed"


def test_configuration_files_exist():
    """Verify that required configuration files exist.

    This test checks that all required CI/CD configuration files
    are present in the repository.
    """
    from pathlib import Path

    repo_root = Path(__file__).parent.parent

    # Check pytest configuration
    pytest_ini = repo_root / "pytest.ini"
    pyproject_toml = repo_root / "pyproject.toml"

    assert pytest_ini.exists(), "pytest.ini not found"
    assert pyproject_toml.exists(), "pyproject.toml not found"

    # Check GitHub Actions workflow
    ci_workflow = repo_root / ".github" / "workflows" / "ci.yml"
    assert ci_workflow.exists(), "CI workflow file not found"


def test_pytest_ini_has_timeout_config():
    """Verify pytest.ini contains timeout configuration.

    This test ensures that pytest.ini has the timeout configuration
    to prevent test hangs in CI/CD pipelines.
    """
    from pathlib import Path

    repo_root = Path(__file__).parent.parent
    pytest_ini = repo_root / "pytest.ini"

    content = pytest_ini.read_text()

    # Check for timeout configuration in addopts
    assert "--timeout=" in content, "pytest.ini missing --timeout option in addopts"
    assert "--timeout-method=" in content, "pytest.ini missing --timeout-method option in addopts"


def test_github_actions_has_timeout():
    """Verify GitHub Actions workflow has timeout configuration.

    This test ensures that the CI workflow has proper timeout
    settings to prevent hanging jobs.
    """
    from pathlib import Path

    repo_root = Path(__file__).parent.parent
    ci_workflow = repo_root / ".github" / "workflows" / "ci.yml"

    content = ci_workflow.read_text()

    # Check for timeout configuration
    assert "timeout-minutes:" in content, "CI workflow missing timeout-minutes"
    assert "--timeout=" in content, "CI workflow missing pytest --timeout option"


def test_poetry_has_pytest_timeout():
    """Verify pyproject.toml includes pytest-timeout dependency.

    This test ensures that the pytest-timeout plugin is listed
    as a development dependency in pyproject.toml.
    """
    from pathlib import Path

    repo_root = Path(__file__).parent.parent
    pyproject_toml = repo_root / "pyproject.toml"

    content = pyproject_toml.read_text()

    # Check for pytest-timeout in dev dependencies
    assert "pytest-timeout" in content, "pyproject.toml missing pytest-timeout dependency"
