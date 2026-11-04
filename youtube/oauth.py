"""YouTube OAuth 2.0 credentials from GitHub secrets (JSON string, base64 or file path)."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("youtube.oauth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def parse_json_secret(raw: str) -> Optional[Dict[str, Any]]:
    """Accept raw JSON, base64-encoded JSON, or a path to a JSON file."""
    if not raw:
        return None
    raw = raw.strip()
    if os.path.exists(raw):
        with open(raw, encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
    except Exception:
        return None


class YouTubeOAuthManager:
    def __init__(self, client_secret_json: str = "", token_json: str = ""):
        self.client_secret_data = client_secret_json
        self.token_data = token_json
        self.last_error = ""

    def _client_info(self) -> Dict[str, Any]:
        data = parse_json_secret(self.client_secret_data) or {}
        return data.get("installed") or data.get("web") or data

    def get_credentials(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError as exc:  # pragma: no cover
            self.last_error = f"google-auth missing: {exc}"
            return None

        token = parse_json_secret(self.token_data)
        if not token:
            self.last_error = "YOUTUBE_TOKEN_JSON secret missing or unreadable"
            logger.info(self.last_error)
            return None
        # Allow a token JSON that only has refresh_token; fill client id/secret from client secret JSON.
        client = self._client_info()
        token.setdefault("client_id", client.get("client_id", ""))
        token.setdefault("client_secret", client.get("client_secret", ""))
        token.setdefault("token_uri", client.get("token_uri", "https://oauth2.googleapis.com/token"))
        try:
            creds = Credentials.from_authorized_user_info(token, token.get("scopes") or SCOPES)
            if not creds.valid and creds.refresh_token:
                creds.refresh(Request())
            return creds
        except Exception as exc:
            self.last_error = f"OAuth refresh failed: {exc}"
            logger.error(self.last_error)
            return None
