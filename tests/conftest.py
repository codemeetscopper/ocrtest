import pytest

from scripts import install_support


@pytest.fixture(autouse=True)
def isolated_installer_source(monkeypatch):
    # CLI installs run in separate processes; tests share one Python process.
    monkeypatch.setattr(install_support, '_package_source',
                        {'mode': 'public', 'index': install_support.PUBLIC_INDEX, 'cert': None})
