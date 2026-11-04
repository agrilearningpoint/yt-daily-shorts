"""YouTube SEO + uploader tests (offline)."""

from __future__ import annotations

import base64
import json

import pytest

from youtube.oauth import YouTubeOAuthManager, parse_json_secret
from youtube.seo import YouTubeSEOFormatter
from youtube.uploader import UploadError, YouTubeUploader


def test_seo_title_formatting():
    formatted = YouTubeSEOFormatter.format_title("भारत का सबसे बड़ा फैसला " * 10)
    assert formatted.endswith("#shorts")
    assert len(formatted) <= 100


def test_seo_description_has_sources_and_disclosure():
    desc = YouTubeSEOFormatter.format_description("क्या आप जानते हैं?", ["https://pib.gov.in/pr1"], ["#shorts"],
                                                 media_credits=["Photo X (CC BY)"])
    assert "https://pib.gov.in/pr1" in desc and "AI" in desc and "Photo X" in desc and "#shorts" in desc


def test_dry_run_uploader():
    res = YouTubeUploader(YouTubeOAuthManager(), dry_run=True).upload_video(
        "output/abc/final_short.mp4", "Test #shorts", "d", ["shorts"])
    assert res["status"] == "dry_run" and res["id"].startswith("mock_")


def test_strict_uploader_without_creds_raises(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 10)
    with pytest.raises(UploadError):
        YouTubeUploader(YouTubeOAuthManager(), dry_run=False, strict=True).upload_video(str(video), "t", "d", [])


def test_parse_json_secret_variants():
    data = {"refresh_token": "x"}
    assert parse_json_secret(json.dumps(data)) == data
    assert parse_json_secret(base64.b64encode(json.dumps(data).encode()).decode()) == data
    assert parse_json_secret("") is None
