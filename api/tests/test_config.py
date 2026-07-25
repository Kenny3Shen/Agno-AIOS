from __future__ import annotations

from importlib.metadata import version as installed_package_version
from unittest.mock import Mock

from api import config


def test_default_app_version_reads_the_project_distribution(
    monkeypatch,
) -> None:
    """OpenAPI must resolve the distribution declared by pyproject.toml."""
    package_version = Mock(return_value="1.0.0")
    monkeypatch.setattr(config, "package_version", package_version)

    assert config._default_app_version() == "1.0.0"
    package_version.assert_called_once_with("T.A.I.S")


def test_default_app_version_matches_installed_project_metadata() -> None:
    """Guard against changing the resolver to a repository/import name."""
    assert config._default_app_version() == installed_package_version("T.A.I.S")
