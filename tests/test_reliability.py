"""Regression tests: news freshness, shared duration rule, duplicate-upload key."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.duration import bounds, estimate_seconds, news_targets
from research.news_collector import NewsCollector
from research.rss_reader import RawArticle
from youtube.uploader import find_existing_upload, publish_key


def _art(title, hours_ago, region="national"):
    when = None if hours_ago is None else datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    a = RawArticle(title, f"https://ex.com/{abs(hash(title))}", "summary text here", when, "Test", "hi")
    a.region = region
    return a


def test_stale_and_undated_news_rejected(monkeypatch):
    c = NewsCollector(allow_offline_fallback=False)
    arts = [_art("ताज़ा खबर संसद में नया विधेयक पेश", 2), _art("पुरानी खबर दो दिन पहले की", 50),
            _art("बिना तारीख वाली खबर का शीर्षक", None), _art("भविष्य की तारीख वाली संदिग्ध खबर", -5)]
    monkeypatch.setattr(c, "_fetch_all", lambda: arts)
    out = c.collect_and_rank_news(target_count=10)
    titles = [o.title for o in out]
    assert titles == ["ताज़ा खबर संसद में नया विधेयक पेश"]


def test_no_fallback_to_old_news(monkeypatch):
    c = NewsCollector(allow_offline_fallback=False)
    monkeypatch.setattr(c, "_fetch_all", lambda: [_art("सिर्फ पुरानी खबर", 30)])
    try:
        c.collect_and_rank_news(target_count=5)
        assert False, "should refuse old news"
    except RuntimeError:
        pass


V = SimpleNamespace(news_national_count=30, news_international_count=6, news_target_duration=120,
                    news_max_duration=135, min_duration=25, max_duration=58)


def test_targets_scale_down_with_few_fresh_stories():
    items = [{"region": "national"}] * 14 + [{"region": "international"}] * 4
    t = news_targets(V, items)
    assert t["national"] == 12 and t["international"] == 3
    assert 55 <= t["seconds"] < 120


def test_duration_rule_is_shared():
    script = {"video_type": "knowledge", "hook": "एक दो तीन", "outro": "",
              "scenes": [{"narration": " ".join(["शब्द"] * 30)}]}
    lo, hi = bounds(V, "knowledge")
    assert estimate_seconds(script) < lo  # a too-short knowledge script is caught by the same rule everywhere


def test_publish_key_is_per_ist_day():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert publish_key("news", datetime(2026, 11, 8, 5, 30, tzinfo=ist)) == "bks-news-20261108"
    # 23:30 UTC on Nov 7 is already Nov 8 in India
    assert publish_key("news", datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)) == "bks-news-20261108"


class _Exec:
    def __init__(self, v):
        self.v = v

    def execute(self):
        return self.v


class _FakeYT:
    def channels(self):
        return SimpleNamespace(list=lambda **k: _Exec(
            {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}))

    def playlistItems(self):
        return SimpleNamespace(list=lambda **k: _Exec(
            {"items": [{"contentDetails": {"videoId": "a"}}, {"contentDetails": {"videoId": "b"}}]}))

    def videos(self):
        return SimpleNamespace(list=lambda **k: _Exec(
            {"items": [{"id": "a", "snippet": {"tags": ["x"]}}, {"id": "b", "snippet": {"tags": ["bks-news-20261108"]}}]}))


def test_duplicate_detected():
    assert find_existing_upload(_FakeYT(), "bks-news-20261108") == "b"
    assert find_existing_upload(_FakeYT(), "bks-news-20261109") is None
