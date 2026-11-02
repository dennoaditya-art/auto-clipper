from __future__ import annotations

from autoclip.config import load_campaigns, load_settings
from autoclip.db import claim_totals, connect, init_db, list_claims, record_claim, set_claim_status


def test_campaign_payout_math():
    settings = load_settings(".")
    campaign = settings.campaign("nautilus-windah-interview")
    assert campaign is not None
    assert campaign.cpm == 4500.0
    assert campaign.min_views == 3000
    # di bawah minimum -> tidak dapat apa pun
    assert campaign.payout(2999) == 0.0
    assert campaign.payout(3000) == 13500.0
    assert campaign.payout(15000) == 67500.0
    # cap maksimum 1.000.000 views per video
    assert campaign.payout(2_000_000) == campaign.payout(1_000_000)


def test_campaign_without_budget_is_not_usable():
    settings = load_settings(".")
    campaign = settings.campaign("windah-mklip")
    assert campaign is not None
    assert campaign.budget_left_pct == 0.0
    assert campaign.usable() is False
    # payout tetap dihitung walau budget habis; usable() yang menahan pemakaian
    assert campaign.payout(199_999) == 0.0
    assert campaign.payout(200_000) == 400_000.0


def test_best_campaign_skips_dead_budget():
    settings = load_settings(".")
    best = settings.best_campaign("windah")
    assert best is not None
    assert best.id != "windah-mklip"
    assert best.budget_left_pct > 0


def test_campaigns_for_source_mapping():
    settings = load_settings(".")
    ids = {c.id for c in settings.campaigns_for_source("windah")}
    assert "windah-mklip" in ids
    assert "nautilus-windah-interview" in ids
    assert settings.campaigns_for_source("jkt48") == ()


def test_load_campaigns_requires_unique_ids(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "campaigns.yaml").write_text(
        "campaigns:\n"
        "  - {id: a, source: windah}\n"
        "  - {id: a, source: windah}\n",
        encoding="utf-8",
    )
    try:
        load_campaigns(tmp_path)
    except Exception as exc:
        assert "duplikat" in str(exc)
    else:
        raise AssertionError("duplikat campaign seharusnya ditolak")


def test_claim_tracking_roundtrip(tmp_path):
    from autoclip.db import create_source, get_source

    db = tmp_path / "t.db"
    conn = connect(db)
    init_db(conn)
    source_id = create_source(conn, "windah-abc.mp4", "h1", 10.0)
    assert source_id is not None
    clip = conn.execute(
        "INSERT INTO clips(source_id, account_id, start, end, file_path, file_hash, "
        "title, topic, scores_json, viral_score, niche_fit, final_score, status, created_at) "
        "VALUES (?, 'utama', 0, 5, 'x.mp4', 'h', 't', 'topik', '{}', 1, 1, 1, 'approved', 'now')",
        (source_id,),
    )
    clip_id = int(clip.lastrowid)
    conn.commit()

    claim_id = record_claim(conn, clip_id, "nautilus-windah", "tiktok", "https://t/1", 15000, 67500.0)
    rows = list_claims(conn)
    assert len(rows) == 1
    assert rows[0]["views"] == 15000
    assert claim_totals(conn)["paid"] == 0.0

    # idempotent: klaim kedua memperbarui baris yang sama
    again = record_claim(conn, clip_id, "nautilus-windah", "tiktok", "https://t/1", 20000, 90000.0)
    assert again == claim_id
    assert len(list_claims(conn)) == 1
    assert list_claims(conn)[0]["views"] == 20000

    set_claim_status(conn, claim_id, "paid")
    assert claim_totals(conn)["paid"] == 90000.0
    conn.close()
