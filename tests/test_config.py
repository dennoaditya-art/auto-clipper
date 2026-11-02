from __future__ import annotations

from pathlib import Path

import pytest

from autoclip.config import ConfigError, load_settings


def test_load_settings(settings):
    assert settings.render.width == 1080
    assert settings.render.height == 1920
    assert settings.selection.clips_per_video == 3
    assert settings.accounts[0].niche == "bisnis"
    assert settings.paths.incoming.exists()
    settings.validate_for_run()


def test_invalid_provider_rejected(settings):
    path = Path(settings.root) / "config" / "settings.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "provider: heuristic", "provider: ngawur"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_settings(settings.root)


def test_rights_risk_accepted_allows_run(settings):
    path = Path(settings.root) / "config" / "settings.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: approved", "status: risk_accepted"
        ),
        encoding="utf-8",
    )
    load_settings(settings.root).validate_for_run()


def test_rights_pending_blocks_run(settings):
    path = Path(settings.root) / "config" / "settings.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: approved", "status: pending"
        ),
        encoding="utf-8",
    )
    reloaded = load_settings(settings.root)
    with pytest.raises(ConfigError):
        reloaded.validate_for_run()
