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


def publish_key(video_type: str, when=None) -> str:
    """One upload per video type per IST day, e.g. 'bks-news-20261108' (stored as a video tag)."""
    import datetime as _dt
    ist = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
    day = (when or _dt.datetime.now(ist)).astimezone(ist).strftime("%Y%m%d")
    return f"bks-{video_type or 'video'}-{day}"


def find_existing_upload(youtube, key: str, scan: int = 20) -> Optional[str]:
    """Look through the channel's latest uploads for one tagged with this publishing key."""
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        return None
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=scan).execute()
    ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
    if not ids:
        return None
    vids = youtube.videos().list(part="snippet", id=",".join(ids)).execute()
    for v in vids.get("items", []):
        if key in (v.get("snippet", {}).get("tags") or []):
            return v["id"]
    return None


class YouTubeUploader:
    def __init__(self, oauth_manager: YouTubeOAuthManager, dry_run: bool = True, strict: bool = False):
        self.oauth_manager = oauth_manager
        self.dry_run = dry_run
        self.strict = strict

    def upload_video(self, video_path: str, title: str, description: str, tags: List[str],
                     category_id: str = "27", privacy_status: str = "public",
                     contains_synthetic_media: bool = True, language: str = "hi",
                     thumbnail_path: Optional[str] = None, publishing_key: str = "",
                     force: bool = False, captions_path: Optional[str] = None,
                     playlist_title: str = "", comment: str = "") -> Optional[Dict[str, Any]]:
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
        if publishing_key:
            tags = list(tags or []) + [publishing_key]
            if not force:
                try:
                    existing = find_existing_upload(youtube, publishing_key)
                except Exception as exc:
                    raise UploadError(f"duplicate check failed, not uploading blind: {exc}") from exc
                if existing:
                    logger.warning("Already uploaded today (%s): %s - skipping duplicate", publishing_key, existing)
                    return {"id": existing, "url": f"https://youtube.com/shorts/{existing}",
                            "status": "duplicate_skipped", "privacy": privacy_status}
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
                found = _verify_after_failure(youtube, publishing_key)
                if found:
                    response = {"id": found}
                    break
                raise UploadError(f"YouTube API error {exc.resp.status}: {exc}") from exc
            except (ConnectionError, TimeoutError, OSError) as exc:
                if retry < 5:
                    retry += 1
                    time.sleep(min(2 ** retry + random.random(), 60))
                    continue
                found = _verify_after_failure(youtube, publishing_key)
                if found:
                    response = {"id": found}
                    break
                raise UploadError(f"upload network failure: {exc}") from exc

        video_id = response.get("id", "")
        if not video_id:
            raise UploadError(f"upload returned no id: {response}")
        logger.info("Upload completed: %s", video_id)

        extras: Dict[str, Any] = {}
        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()
                extras["thumbnail"] = "set"
            except Exception as exc:  # Shorts/unverified channels often can't set thumbnails
                extras["thumbnail"] = f"not set: {str(exc)[:100]}"
                logger.info("Thumbnail not set (non-fatal): %s", str(exc)[:160])
        extras.update(finish_upload(youtube, video_id, captions_path, playlist_title, comment, language))
        logger.info("Post-upload: %s", extras)

        upload_status = (response.get("status") or {}).get("uploadStatus", "")
        return {"id": video_id, "url": f"https://youtube.com/shorts/{video_id}", "status": upload_status or "uploaded",
                "privacy": privacy_status, "extras": extras}


def finish_upload(youtube, video_id: str, captions_path: Optional[str], playlist_title: str, comment: str,
                  language: str = "hi") -> Dict[str, Any]:
    """Non-fatal extras after an upload: Hindi caption track (SRT), daily-news playlist, first comment."""
    out: Dict[str, Any] = {}
    from googleapiclient.http import MediaFileUpload
    if captions_path and Path(captions_path).exists():
        try:
            youtube.captions().insert(part="snippet", body={"snippet": {
                "videoId": video_id, "language": language, "name": "हिन्दी", "isDraft": False}},
                media_body=MediaFileUpload(captions_path, mimetype="application/octet-stream")).execute()
            out["captions"] = "uploaded"
        except Exception as exc:
            out["captions"] = f"failed: {str(exc)[:100]}"
    if playlist_title:
        try:
            pid = ""
            req = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
            for pl in req.get("items", []):
                if pl["snippet"]["title"] == playlist_title:
                    pid = pl["id"]
                    break
            if not pid:
                pid = youtube.playlists().insert(part="snippet,status", body={
                    "snippet": {"title": playlist_title, "defaultLanguage": language},
                    "status": {"privacyStatus": "public"}}).execute()["id"]
            youtube.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            out["playlist"] = pid
        except Exception as exc:
            out["playlist"] = f"failed: {str(exc)[:100]}"
    if comment:
        try:
            youtube.commentThreads().insert(part="snippet", body={"snippet": {
                "videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": comment}}}}).execute()
            out["comment"] = "posted (pin it in YouTube Studio: the API cannot pin)"
        except Exception as exc:
            out["comment"] = f"failed: {str(exc)[:100]}"
    return out


def _verify_after_failure(youtube, key: str) -> Optional[str]:
    """A timed-out upload may still have landed: check the channel before anyone retries."""
    if not key:
        return None
    try:
        time.sleep(20)
        found = find_existing_upload(youtube, key)
        if found:
            logger.warning("Upload errored but video %s exists on the channel - treating as uploaded", found)
        return found
    except Exception:
        return None
