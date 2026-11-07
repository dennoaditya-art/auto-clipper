"""CLI harus bisa diimpor: entry point task terjadwal bergantung padanya."""

import autoclip.cli as cli


def test_cli_imports():
    assert callable(cli.main)
