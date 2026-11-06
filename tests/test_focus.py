from __future__ import annotations

from dataclasses import replace

from autoclip.config import FocusConfig, Source
from autoclip.select import _focus_bonus


def _source(source_id: str, **kwargs) -> Source:
    base = dict(
        id=source_id,
        url="",
        account_id="utama",
        enabled=True,
        rights_approved=True,
        rights_risk_accepted=False,
        rights_reference="tes",
        latest=0,
        fallback_popular=False,
        campaign="",
        watermark="",
        hashtags="",
        credit="",
    )
    base.update(kwargs)
    return Source(**base)


def test_focus_bonus_counts_keywords():
    focus = FocusConfig(
        sources=("windah3",), keywords=("opah", "roblox"), keyword_bonus=2.5
    )
    assert _focus_bonus("Opah nya seram, ini roblox", focus) == 5.0
    assert _focus_bonus("main gta biasa", focus) == 0.0


def test_focus_sources_filter(settings):
    focus = FocusConfig(
        sources=("windah3",), keywords=(), keyword_bonus=0.0
    )
    settings = replace(
        settings,
        focus=focus,
        sources=(
            _source("windah3"),
            _source("jkt48"),
            _source("windah", enabled=False),
        ),
    )
    assert [s.id for s in settings.focus_active_sources()] == ["windah3"]


def test_focus_sources_empty_means_all(settings):
    settings = replace(
        settings,
        focus=FocusConfig(sources=(), keywords=(), keyword_bonus=0.0),
        sources=(_source("windah3"), _source("jkt48")),
    )
    assert {s.id for s in settings.focus_active_sources()} == {"windah3", "jkt48"}
