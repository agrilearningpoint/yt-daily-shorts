"""Secure YouTube OAuth 2.0 authentication and token management."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("youtube.oauth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


class YouTubeOAuthManager:
    """Manages Google OAuth2 credentials without exposing secrets."""

    def __init__(self, client_secret_json: str = "", token_json: str = ""):
        self.client_secret_data = client_secret_json
        self.token_data = token_json

    def get_credentials(self):
        """Construct Google Credentials from JSON strings or env."""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            if not self.token_data:
                logger.info("No YOUTUBE_TOKEN_JSON provided. Uploads will run in DRY_RUN mode.")
                return None

            raw_token = self.token_data.strip()
            # If passed as file path
            if os.path.exists(raw_token):
                with open(raw_token, "r", encoding="utf-8") as f:
                    token_dict = json.load(f)
            else:
                token_dict = json.loads(raw_token)

            creds = Credentials.from_authorized_user_info(token_dict, SCOPES)

            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired YouTube OAuth credentials")
                creds.refresh(Request())

            return creds
        except Exception as exc:
            logger.warning("Failed to initialize Google OAuth credentials: %s", exc)
            return None
