from __future__ import annotations

from pathlib import Path

from autoclip.config import Campaign, Settings, Source, UploadConfig, load_settings


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


def test_source_meta_matches_suffixed_key(tmp_path):
    """File `windah3-...` harus dianggap sumber `windah`, bukan global."""
    from autoclip.publish import _source_meta

    settings = _settings(tmp_path)
    conn = _Conn("windah3-sQS6zVkqYGA.mp4")
    hashtags, credit = _source_meta(settings, conn, {"source_id": 1})
    assert hashtags == "#windah #gaming"
    assert credit == "Sumber: Windah Basudara."


def test_description_has_no_internal_topic(tmp_path):
    from autoclip.youtube import _description

    clip = {"title": "Judul", "topic": "salah sambung lucu"}
    desc = _description(clip, UploadConfig("#tag", "Sumber: X.", True, "", 6.0))
    assert "salah sambung lucu" not in desc
    assert "Sumber: X." in desc


def _campaign(**over) -> Campaign:
    base = dict(
        id="windah-mklip",
        label="Windah",
        source="windah",
        platforms=("tiktok",),
        mode="per_video",
        cpm=1000.0,
        fixed_payout=0.0,
        min_views=0,
        max_claim_views=200_000,
        payout_methods=("dana",),
        hashtags="#windahMKLIP2 #motionklip #ezklip",
        watermark="MKLP",
        watermark_image="",
        required_tag="",
        budget_left_pct=0.0,
        max_videos_per_month=30,
        active=True,
        verified=True,
        note="",
    )
    base.update(over)
    return Campaign(**base)


class _RowConn:
    def __init__(self, path: str) -> None:
        self._row = (path,)

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return self._row


def test_campaign_hashtags_still_win_when_flag_off(tmp_path):
    """Tanpa flag, hashtag campaign tetap dipakai (perilaku lama)."""
    from dataclasses import replace

    from autoclip.publish import _source_meta

    settings = replace(
        _settings(tmp_path),
        campaigns=(_campaign(platforms=("tiktok", "youtube")),),
    )
    hashtags, _ = _source_meta(settings, _Conn("windah-a.mp4"), {"source_id": 1}, "youtube")
    assert hashtags == "#windahMKLIP2 #motionklip #ezklip"


def test_youtube_without_campaign_skips_campaign_hashtags(tmp_path):
    """Sumber tanpa lisensi campaign tidak boleh memasang hashtag campaign."""
    from dataclasses import replace

    from autoclip.publish import _source_meta

    sources = tuple(
        replace(s, youtube_without_campaign=True) if s.id == "windah" else s
        for s in _settings(tmp_path).sources
    )
    settings = replace(_settings(tmp_path), campaigns=(_campaign(),), sources=sources)
    hashtags, credit = _source_meta(
        settings, _Conn("windah-a.mp4"), {"source_id": 1}, "youtube"
    )
    assert hashtags == "#windah #gaming"
    assert "mklip" not in hashtags.lower()
    assert credit == "Sumber: Windah Basudara."
    # TikTok tetap ikut campaign.
    tiktok, _ = _source_meta(settings, _Conn("windah-a.mp4"), {"source_id": 1}, "tiktok")
    assert tiktok == "#windahMKLIP2 #motionklip #ezklip"


def test_youtube_allowed_bypasses_tiktok_only_campaign(tmp_path):
    from dataclasses import replace

    from autoclip.publish import _youtube_allowed

    campaign = _campaign(platforms=("tiktok",), budget_left_pct=1.0)
    settings = replace(_settings(tmp_path), campaigns=(campaign,))
    conn = _RowConn("windah-a.mp4")
    assert _youtube_allowed(settings, conn, 1) is False

    sources = tuple(
        replace(s, youtube_without_campaign=True) if s.id == "windah" else s
        for s in settings.sources
    )
    assert _youtube_allowed(replace(settings, sources=sources), conn, 1) is True

def test_upload_for_carries_title_suffix(tmp_path):
    """Judul YouTube memakai pola niche, bukan potongan transkrip mentah."""
    from dataclasses import replace

    from autoclip.publish import _upload_for
    from autoclip.youtube import _metadata

    sources = tuple(
        replace(s, title_suffix=" - Momen Kocak Windah Basudara")
        if s.id == "windah"
        else s
        for s in _settings(tmp_path).sources
    )
    settings = replace(_settings(tmp_path), sources=sources)
    clip = {"source_id": 1, "title": "Nemu Area Baru"}
    upload = _upload_for(settings, _Conn("windah-a.mp4"), clip)
    assert upload.title_suffix == " - Momen Kocak Windah Basudara"
    meta = _metadata(clip, "private", upload)
    assert meta["snippet"]["title"] == "Nemu Area Baru - Momen Kocak Windah Basudara"
