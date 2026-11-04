from __future__ import annotations

from pathlib import Path

from autoclip.config import Settings, Source, UploadConfig, load_settings


def _settings(tmp_path: Path) -> Settings:
    real = load_settings(Path(__file__).resolve().parents[1])
    sources = (
        Source(
            id="windah",
            url="https://example.test/windah",
            account_id="utama",
            enabled=True,
            rights_approved=False,
            rights_risk_accepted=True,
            rights_reference="uji",
            latest=1,
            fallback_popular=False,
            campaign="",
            watermark="",
            hashtags="#windah #gaming",
            credit="Sumber: Windah Basudara.",
        ),
        Source(
            id="jkt48",
            url="https://example.test/jkt48",
            account_id="utama",
            enabled=True,
            rights_approved=False,
            rights_risk_accepted=True,
            rights_reference="uji",
            latest=1,
            fallback_popular=True,
            campaign="",
            watermark="",
            hashtags="#jkt48 #idol",
            credit="Sumber: JKT48 TV.",
        ),
    )
    return Settings(
        root=tmp_path,
        paths=real.paths,
        transcription=real.transcription,
        selection=real.selection,
        render=real.render,
        upload=UploadConfig(
            hashtags="#global",
            credit="Sumber: global.",
            thumbnail=True,
            schedule_start="",
            schedule_interval_hours=6.0,
        ),
        safety=real.safety,
        accounts=real.accounts,
        sources=sources,
        campaigns=(),
    )


class _Conn:
    def __init__(self, path: str) -> None:
        self._row = {"path": path}

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return self._row


def test_source_meta_uses_source_specific_values(tmp_path):
    from autoclip.publish import _source_meta

    settings = _settings(tmp_path)
    clip = {"source_id": 1}
    conn = _Conn("windah-JFax1qrU_ow.mp4")
    hashtags, credit = _source_meta(settings, conn, clip)
    assert hashtags == "#windah #gaming"
    assert credit == "Sumber: Windah Basudara."
    assert "jkt48" not in hashtags.lower()


def test_source_meta_unknown_source_uses_own_name_not_global(tmp_path):
    """Sumber tak terdaftar tidak boleh meminjam metadata sumber lain."""
    from autoclip.publish import _source_meta

    settings = _settings(tmp_path)
    conn = _Conn("radityadika-mQFROnZBqk0.mp4")
    hashtags, credit = _source_meta(settings, conn, {"source_id": 1})
    assert hashtags == "#radityadika #shortsindonesia"
    assert "jkt48" not in hashtags.lower()
    assert "Radityadika" in credit


def test_description_has_no_internal_topic(tmp_path):
    from autoclip.youtube import _description

    clip = {"title": "Judul", "topic": "salah sambung lucu"}
    desc = _description(clip, UploadConfig("#tag", "Sumber: X.", True, "", 6.0))
    assert "salah sambung lucu" not in desc
    assert "Sumber: X." in desc
