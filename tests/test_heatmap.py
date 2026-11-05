from pathlib import Path

from autoclip import heatmap


HTML = (
    '{"heatmap":{"markers":['
    '{"startMillis":"10000","durationMillis":"50230",'
    '"intensityScoreNormalized":0.4},'
    '{"startMillis":"300000","durationMillis":"50230",'
    '"intensityScoreNormalized":0.95}]}}'
)


def test_parse_markers():
    markers = heatmap.parse(HTML)
    assert markers == [(10.0, 60.23, 0.4), (300.0, 350.23, 0.95)]


def test_bonus_only_for_replay_peak():
    markers = heatmap.parse(HTML)
    quiet = heatmap.bonus(markers, 100.0, 140.0)
    peak = heatmap.bonus(markers, 305.0, 345.0)
    assert quiet == 0.0
    assert peak > 10.0


def test_bonus_empty_markers():
    assert heatmap.bonus([], 0.0, 30.0) == 0.0


def test_video_id_from_filename_and_url():
    assert heatmap.video_id("windah3-sQS6zVkqYGA.mp4") == "sQS6zVkqYGA"
    assert (
        heatmap.video_id("https://www.youtube.com/watch?v=b0uUjcOLLqk")
        == "b0uUjcOLLqk"
    )
    assert heatmap.video_id("tanpa-id.mp4") is None


def test_fetch_uses_cache(tmp_path: Path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("jaringan tidak boleh dipanggil saat cache segar")

    monkeypatch.setattr(heatmap.urllib.request, "urlopen", boom)
    cache = tmp_path / "heat"
    cache.mkdir()
    (cache / "sQS6zVkqYGA.json").write_text(
        "[[1.0, 2.0, 0.5]]", encoding="utf-8"
    )
    assert heatmap.fetch("windah3-sQS6zVkqYGA.mp4", cache) == [(1.0, 2.0, 0.5)]
