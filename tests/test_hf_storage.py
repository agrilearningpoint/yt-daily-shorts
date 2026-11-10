"""HF Hub artefact storage: no-op safety, upload plan, state backup."""

from __future__ import annotations

import json
from pathlib import Path

from core.hf_storage import HFArtifactStore, store_from_config


class FakeApi:
    def __init__(self):
        self.created = []
        self.uploads = []
        self.folders = []

    def create_repo(self, repo_id, repo_type, private, exist_ok):
        self.created.append((repo_id, repo_type, private, exist_ok))
        return repo_id

    def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message=""):
        self.uploads.append((Path(path_or_fileobj).name, path_in_repo, repo_type))
        return f"commit/{path_in_repo}"

    def upload_folder(self, folder_path, path_in_repo, repo_id, repo_type,
                      ignore_patterns=None, commit_message=""):
        self.folders.append((Path(folder_path).name, path_in_repo, tuple(ignore_patterns or ())))
        return f"tree/{path_in_repo}"


def test_disabled_without_repo_or_token():
    assert HFArtifactStore().enabled is False
    assert HFArtifactStore(repo_id="x/y").enabled is False        # token missing
    assert HFArtifactStore(token="hf_x").enabled is False         # repo missing
    assert HFArtifactStore(repo_id="x/y", token="hf_x").enabled is True


def test_disabled_store_never_touches_network(tmp_path):
    store = HFArtifactStore()
    f = tmp_path / "a.mp4"; f.write_bytes(b"x")
    assert store.upload_file(f, "videos/a.mp4") is None
    assert store.upload_video("vid1", {"final_short.mp4": str(f)}) == {}
    assert store.backup_state([str(f)]) == {}
    assert store.upload_dir(tmp_path) is None


def test_upload_video_plans_paths(monkeypatch, tmp_path):
    store = HFArtifactStore(repo_id="Rajaagri/yt-daily-shorts-artifacts", token="hf_x")
    fake = FakeApi()
    monkeypatch.setattr(store, "_client", lambda: fake)

    vid = tmp_path / "final_short.mp4"; vid.write_bytes(b"v" * 10)
    srt = tmp_path / "captions.srt"; srt.write_text("1")
    thumb = tmp_path / "thumb.jpg"; thumb.write_bytes(b"jpg")

    urls = store.upload_video(
        "abc123",
        {"final_short.mp4": str(vid), "captions.srt": str(srt), "thumbnail.jpg": str(thumb)},
        meta={"title": "test"},
        day="2026-11-10",
    )
    assert set(urls) == {"final_short.mp4", "captions.srt", "thumbnail.jpg", "manifest.json"}
    paths = [p for _n, p, _t in fake.uploads]
    assert "videos/2026-11-10/abc123/final_short.mp4" in paths
    assert "videos/2026-11-10/abc123/manifest.json" in paths
    assert all(t == "dataset" for _n, _p, t in fake.uploads)
    assert urls["final_short.mp4"].startswith("https://huggingface.co/datasets/Rajaagri/yt-daily-shorts-artifacts/resolve/main/")


def test_upload_dir_skips_intermediate_frames(monkeypatch, tmp_path):
    store = HFArtifactStore(repo_id="r/x", token="hf_x")
    fake = FakeApi()
    monkeypatch.setattr(store, "_client", lambda: fake)
    (tmp_path / "final_short.mp4").write_bytes(b"v")
    url = store.upload_dir(tmp_path, "videos/2026-11-10/abc")
    assert url and fake.folders
    patterns = fake.folders[0][2]
    assert any("_clips" in p for p in patterns) and any("*.wav" in p for p in patterns)


def test_state_backup_uploads_existing_files(monkeypatch, tmp_path):
    store = HFArtifactStore(repo_id="r/x", token="hf_x")
    fake = FakeApi()
    monkeypatch.setattr(store, "_client", lambda: fake)
    db = tmp_path / "yt_shorts.db"; db.write_bytes(b"db")
    hist = tmp_path / "history.json"; hist.write_text(json.dumps({"runs": []}))
    urls = store.backup_state([str(db), str(hist), str(tmp_path / "missing.db")])
    assert set(urls) == {"yt_shorts.db", "history.json"}
    assert all(p.startswith("state/") for _n, p, _t in fake.uploads)


def test_store_from_config_reads_media_settings():
    class Media:
        hf_token = "hf_x"
        hf_repo_id = "Rajaagri/yt-daily-shorts-artifacts"
        hf_storage_private = False

    class Cfg:
        media = Media()

    store = store_from_config(Cfg())
    assert store.enabled and store.repo_id.endswith("yt-daily-shorts-artifacts")
    assert store.private is False


def test_image_generator_defaults_are_hf_recommended():
    from video.image_generator import DEFAULT_IMAGE_MODELS
    assert DEFAULT_IMAGE_MODELS[0] == "black-forest-labs/FLUX.1-Krea-dev"
    assert "Qwen/Qwen-Image" in DEFAULT_IMAGE_MODELS


# --------------------------------------------------------------------------- #
# Free AI image backends: credits → Space → Pollinations
# --------------------------------------------------------------------------- #
def test_image_backend_order_is_credits_space_pollinations():
    from video.image_generator import AIImageGenerator

    gen = AIImageGenerator("hf_dummy")
    order = [m.__name__ for m in (gen._via_credits, gen._via_space, gen._via_pollinations)]
    assert order == ["_via_credits", "_via_space", "_via_pollinations"]
    assert gen.spaces[0].endswith("FLUX.1-schnell")      # fastest / cheapest quota


def test_image_402_marks_credits_dead_but_keeps_free_backends(monkeypatch):
    from video.image_generator import AIImageGenerator

    gen = AIImageGenerator("hf_dummy")

    class _Fake:
        def text_to_image(self, *a, **k):
            raise RuntimeError("402 Payment Required: purchase pre-paid credits")

    gen._client = _Fake()
    assert gen._via_credits("x", __import__("pathlib").Path("/tmp/none.jpg")) is False
    assert gen.dead is True
    assert gen._via_credits("x", __import__("pathlib").Path("/tmp/none.jpg")) is False
    # the free route must stay available even when credits are gone
    assert gen.space_dead is False and gen.pollinations_dead is False


def test_image_space_failure_falls_through_to_pollinations(monkeypatch):
    import pathlib
    from PIL import Image
    from video.image_generator import AIImageGenerator

    gen = AIImageGenerator("hf_dummy")

    def boom(text, out_file):
        raise RuntimeError("space down")

    gen._via_credits = lambda t, o: False
    gen._via_space = boom
    src = pathlib.Path("/tmp/_src.jpg")
    Image.new("RGB", (32, 64), (10, 20, 30)).save(src)

    def fake_poll(text, out_file):
        AIImageGenerator._normalise_image(str(src), out_file)
        return True

    gen._via_pollinations = fake_poll
    out = gen.generate("a scene", "/tmp/_out_free.jpg")
    assert out == "/tmp/_out_free.jpg"
    assert pathlib.Path(out).stat().st_size > 0


def test_image_normalise_converts_webp_to_jpeg():
    import pathlib
    from PIL import Image
    from video.image_generator import AIImageGenerator

    src = pathlib.Path("/tmp/_n.webp")
    Image.new("RGB", (48, 96), (200, 30, 30)).save(src, "WEBP")
    dst = pathlib.Path("/tmp/_n.jpg")
    AIImageGenerator._normalise_image(str(src), dst)
    with Image.open(dst) as im:
        assert im.format == "JPEG" and im.size == (48, 96)
