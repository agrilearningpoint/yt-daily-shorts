"""YouTube Data API v3 uploader with resumable upload, retries and DRY_RUN."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from youtube.oauth import YouTubeOAuthManager

logger = logging.getLogger("youtube.uploader")
RETRIABLE_STATUS = {500, 502, 503, 504}


class UploadError(RuntimeError):
    pass


class YouTubeUploader:
    def __init__(self, oauth_manager: YouTubeOAuthManager, dry_run: bool = True, strict: bool = False):
        self.oauth_manager = oauth_manager
        self.dry_run = dry_run
        self.strict = strict

    def upload_video(self, video_path: str, title: str, description: str, tags: List[str],
                     category_id: str = "27", privacy_status: str = "public",
                     contains_synthetic_media: bool = True, language: str = "hi",
                     thumbnail_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.dry_run:
            logger.info("⚡ [DRY_RUN] Skipping YouTube upload: %s", title)
            sim = f"mock_{Path(video_path).parent.name}"
            return {"id": sim, "url": f"https://youtube.com/shorts/{sim}", "status": "dry_run"}

        if not Path(video_path).exists():
            raise UploadError(f"video file missing: {video_path}")
        creds = self.oauth_manager.get_credentials()
        if not creds:
            msg = f"No valid YouTube credentials: {self.oauth_manager.last_error}"
            if self.strict:
                raise UploadError(msg)
            logger.warning(msg)
            sim = f"dry_run_{Path(video_path).parent.name}"
            return {"id": sim, "url": f"https://youtube.com/shorts/{sim}", "status": "dry_run_missing_creds"}

        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        body = {
            "snippet": {"title": title[:100], "description": description[:5000], "tags": tags,
                        "categoryId": str(category_id), "defaultLanguage": language,
                        "defaultAudioLanguage": language},
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": bool(contains_synthetic_media)},
        }
        media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        retry = 0
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.info("Uploaded %d%%", int(status.progress() * 100))
            except HttpError as exc:
                if exc.resp.status in RETRIABLE_STATUS and retry < 5:
                    retry += 1
                    time.sleep(min(2 ** retry + random.random(), 60))
                    continue
                raise UploadError(f"YouTube API error {exc.resp.status}: {exc}") from exc
            except (ConnectionError, TimeoutError, OSError) as exc:
                if retry < 5:
                    retry += 1
                    time.sleep(min(2 ** retry + random.random(), 60))
                    continue
                raise UploadError(f"upload network failure: {exc}") from exc

        video_id = response.get("id", "")
        if not video_id:
            raise UploadError(f"upload returned no id: {response}")
        logger.info("Upload completed: %s", video_id)

        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
            except Exception as exc:  # Shorts/unverified channels often can't set thumbnails
                logger.info("Thumbnail not set (non-fatal): %s", str(exc)[:160])

        upload_status = (response.get("status") or {}).get("uploadStatus", "")
        return {"id": video_id, "url": f"https://youtube.com/shorts/{video_id}", "status": upload_status or "uploaded",
                "privacy": privacy_status}
