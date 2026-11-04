"""YouTube video uploader using YouTube Data API v3 with robust DRY_RUN support."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from youtube.oauth import YouTubeOAuthManager

logger = logging.getLogger("youtube.uploader")


class YouTubeUploader:
    """Publishes videos to YouTube via official Data API v3."""

    def __init__(self, oauth_manager: YouTubeOAuthManager, dry_run: bool = True):
        self.oauth_manager = oauth_manager
        self.dry_run = dry_run

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        category_id: str = "22",
        privacy_status: str = "private"
    ) -> Optional[Dict[str, Any]]:
        """Upload video file to YouTube Shorts."""
        if self.dry_run:
            logger.info("⚡ [DRY_RUN ACTIVE] Skipping actual YouTube upload.")
            logger.info("Simulated Video Title: %s", title)
            logger.info("Simulated File: %s", video_path)
            simulated_id = f"mock_{Path(video_path).stem}"
            return {
                "id": simulated_id,
                "url": f"https://youtube.com/shorts/{simulated_id}",
                "status": "dry_run_success"
            }

        creds = self.oauth_manager.get_credentials()
        if not creds:
            logger.warning("No valid OAuth credentials found. Switching to DRY_RUN.")
            simulated_id = f"dry_run_{Path(video_path).stem}"
            return {
                "id": simulated_id,
                "url": f"https://youtube.com/shorts/{simulated_id}",
                "status": "dry_run_missing_creds"
            }

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(
                video_path,
                chunksize=-1,
                resumable=True,
                mimetype="video/mp4"
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info("Uploaded %d%%...", int(status.progress() * 100))

            video_id = response.get("id", "")
            logger.info("Upload completed! Video ID: %s", video_id)
            return {
                "id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}",
                "status": "published"
            }
        except Exception as exc:
            logger.error("YouTube upload failed: %s", exc)
            return None
