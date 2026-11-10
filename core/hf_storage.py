"""Hugging Face Hub artifact storage.

Rendered videos, captions, thumbnails, manifests and the pipeline state are
mirrored to a free HF **dataset** repository, so long-form renders (next
milestone) are not limited by GitHub Actions artifact retention (7 days) or
repo size caps.

Free tier covers dataset storage; only *inference* needs credits. Every call
degrades to a silent no-op when no token / repo is configured, so the pipeline
never breaks because of storage.

Usage::

    store = HFArtifactStore(repo_id="Rajaagri/yt-daily-shorts-artifacts",
                            token=cfg.media.hf_token)
    if store.enabled:
        urls = store.upload_video("abc123", {"final_short.mp4": path, ...})
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger("core.hf_storage")

# Intermediate frames / clips are huge and reproducible: never upload them.
_SKIP_PATTERNS = [
    "_clips/*", "*.wav", "*.pyc", "__pycache__/*", ".git/*",
    "frames/*", "*.tmp", "*.part",
]


class HFArtifactStore:
    """Thin, fail-safe wrapper around ``huggingface_hub.HfApi``."""

    def __init__(self, repo_id: str = "", token: str = "", repo_type: str = "dataset",
                 private: bool = True, token_override: Optional[str] = None) -> None:
        self.repo_id = (repo_id or "").strip()
        self.token = token_override or token or ""
        self.repo_type = repo_type
        self.private = private
        self.last_error = ""
        self._api = None

    # ------------------------------------------------------------------ setup
    @property
    def enabled(self) -> bool:
        return bool(self.repo_id and self.token)

    def _client(self):
        if self._api is not None:
            return self._api
        from huggingface_hub import HfApi   # imported lazily: optional dependency

        self._api = HfApi(token=self.token)
        return self._api

    def ensure_repo(self) -> bool:
        if not self.enabled:
            return False
        try:
            self._client().create_repo(repo_id=self.repo_id, repo_type=self.repo_type,
                                       private=self.private, exist_ok=True)
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:300]
            logger.warning("HF storage: cannot open %s (%s)", self.repo_id, self.last_error)
            return False

    # ---------------------------------------------------------------- uploads
    def upload_file(self, local_path: str | Path, path_in_repo: str,
                    commit_message: str = "") -> Optional[str]:
        """Upload one file; returns the public/private resolve URL."""
        if not self.enabled or not Path(local_path).exists():
            return None
        try:
            self._client().upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=path_in_repo,
                repo_id=self.repo_id,
                repo_type=self.repo_type,
                commit_message=commit_message or f"upload {Path(local_path).name}",
            )
            kind = "datasets" if self.repo_type == "dataset" else "models"
            return f"https://huggingface.co/{kind}/{self.repo_id}/resolve/main/{path_in_repo}"
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("HF storage upload failed for %s: %s", path_in_repo, self.last_error)
            return None

    def upload_video(self, video_id: str, files: Dict[str, str],
                     meta: Optional[Dict[str, Any]] = None,
                     day: Optional[str] = None) -> Dict[str, str]:
        """Upload one video's artefacts under ``videos/<YYYY-MM-DD>/<video_id>/``.

        ``files`` maps a repo-relative name to a local path, e.g.
        ``{"final_short.mp4": "...", "captions.srt": "...", "thumbnail.jpg": "..."}``.
        """
        if not self.enabled:
            return {}
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prefix = f"videos/{day}/{video_id}"
        urls: Dict[str, str] = {}
        for name, path in files.items():
            if not path:
                continue
            url = self.upload_file(path, f"{prefix}/{Path(name).name}",
                                   commit_message=f"video {video_id}: {Path(name).name}")
            if url:
                urls[Path(name).name] = url
        if meta is not None:
            manifest_path = Path(files.get("__manifest_dir__", "") or ".") / f"manifest_{video_id}.json"
            try:
                payload = {"video_id": video_id, "day": day,
                           "uploaded_at": datetime.now(timezone.utc).isoformat(),
                           "files": urls, **meta}
                manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
                url = self.upload_file(manifest_path, f"{prefix}/manifest.json", "manifest")
                if url:
                    urls["manifest.json"] = url
                manifest_path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                logger.debug("HF storage manifest skipped: %s", exc)
        return urls

    def upload_dir(self, local_dir: str | Path, path_in_repo: str = "",
                   ignore: Optional[Iterable[str]] = None,
                   commit_message: str = "sync") -> Optional[str]:
        """Upload a whole directory (chunked/resumable for long-video artefacts)."""
        local = Path(local_dir)
        if not self.enabled or not local.exists():
            return None
        try:
            self._client().upload_folder(
                folder_path=str(local),
                path_in_repo=path_in_repo or local.name,
                repo_id=self.repo_id,
                repo_type=self.repo_type,
                ignore_patterns=list(ignore or _SKIP_PATTERNS),
                commit_message=commit_message,
            )
            return f"https://huggingface.co/{'datasets' if self.repo_type == 'dataset' else 'models'}/{self.repo_id}/tree/main/{path_in_repo or local.name}"
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("HF storage folder upload failed: %s", self.last_error)
            return None

    def backup_state(self, paths: Iterable[str], prefix: str = "state") -> Dict[str, str]:
        """Mirror the SQLite DB / history JSON so a fresh runner can restore them."""
        urls: Dict[str, str] = {}
        for path in paths:
            if not path or not Path(path).exists():
                continue
            url = self.upload_file(path, f"{prefix}/{Path(path).name}", "state backup")
            if url:
                urls[Path(path).name] = url
        return urls


def store_from_config(config) -> HFArtifactStore:
    """Build a store from ``AppConfig`` (returns a disabled store when unset)."""
    media = getattr(config, "media", None)
    return HFArtifactStore(
        repo_id=getattr(media, "hf_repo_id", "") or os.getenv("YT_HF_REPO_ID", ""),
        token=getattr(media, "hf_token", "") or os.getenv("YT_HF_TOKEN", ""),
        private=bool(getattr(media, "hf_storage_private", True)),
    )
