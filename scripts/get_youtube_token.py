"""One-time helper: create the YOUTUBE_TOKEN_JSON secret on your own computer.

Steps
1. Google Cloud Console -> APIs & Services -> enable "YouTube Data API v3".
2. OAuth consent screen -> User type External -> add yourself as Test user,
   then click "PUBLISH APP" (In production) so the refresh token does not
   expire after 7 days.
3. Credentials -> Create OAuth client ID -> "Desktop app" -> download JSON as
   client_secret.json next to this script (same JSON you put in the
   YOUTUBE_CLIENT_SECRET_JSON secret).
4. pip install google-auth-oauthlib
   python scripts/get_youtube_token.py
   A browser opens: sign in with the Google account that OWNS the channel
   (pick the channel/brand account if asked) and allow access.
5. Copy the printed JSON into GitHub -> Settings -> Secrets -> Actions ->
   New secret named YOUTUBE_TOKEN_JSON.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main() -> None:
    secret = Path(sys.argv[1] if len(sys.argv) > 1 else "client_secret.json")
    if not secret.exists():
        sys.exit(f"Client secret file not found: {secret}")
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    data = json.loads(creds.to_json())
    print("\n===== Copy everything below into the YOUTUBE_TOKEN_JSON secret =====\n")
    print(json.dumps(data))
    print("\n=====================================================================")


if __name__ == "__main__":
    main()
