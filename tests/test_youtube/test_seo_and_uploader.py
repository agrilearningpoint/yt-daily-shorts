"""Unit tests for YouTube SEO formatting and upload simulation."""

from __future__ import annotations

from youtube.oauth import YouTubeOAuthManager
from youtube.seo import YouTubeSEOFormatter
from youtube.uploader import YouTubeUploader


def test_seo_title_formatting():
    raw = "भारत का सबसे बड़ा फैसला जिसने सबको चौंका दिया"
    formatted = YouTubeSEOFormatter.format_title(raw)
    assert "#shorts" in formatted
    assert len(formatted) <= 100


def test_seo_description_formatting():
    sources = ["https://pib.gov.in/pr1", "https://ddnews.gov.in/pr2"]
    desc = YouTubeSEOFormatter.format_description("क्या आप जानते हैं?", sources, ["#shorts", "#india"])
    assert "https://pib.gov.in/pr1" in desc
    assert "Verified Sources" in desc
    assert "#shorts" in desc


def test_dry_run_uploader():
    oauth = YouTubeOAuthManager()
    uploader = YouTubeUploader(oauth, dry_run=True)
    res = uploader.upload_video(
        video_path="output/test/video.mp4",
        title="Test #shorts",
        description="Test desc",
        tags=["shorts"]
    )
    assert res is not None
    assert res["status"] == "dry_run_success"
    assert "mock_" in res["id"]
