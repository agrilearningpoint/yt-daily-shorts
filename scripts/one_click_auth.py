"""One command, one browser click: mint a fresh YOUTUBE_TOKEN_JSON — verified before it is printed.

    python scripts/one_click_auth.py

What it does, in order:
  1. opens your browser on the Google consent screen (PKCE, offline access, prompt=consent)
  2. catches the http://localhost redirect itself — you never copy a code
  3. exchanges it for a refresh token
  4. VERIFIES it with a real YouTube API call (channels.list) and prints the channel name
  5. writes token.json next to this script and prints the exact JSON for the secret

Optional, fully automatic secret update (needs a GitHub token with `secrets: write`):
    GH_TOKEN=ghp_xxx python scripts/one_click_auth.py --set-github-secret
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
REPO = "agrilearningpoint/yt-daily-shorts"


class _UrlCapturer:
    def format(self, url: str = "") -> str:
        Path("data").mkdir(exist_ok=True)
        Path("data/oauth_url.txt").write_text(url, encoding="utf-8")
        print(f"\n=======================================================\nAUTH_URL: {url}\n=======================================================\n", flush=True)
        return f"\nOpen this link if browser did not open:\n{url}\n"


def authorize(secret_path: Path, port: int):
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    print("\nA browser window will open. Sign in with the Google account that OWNS the channel,", flush=True)
    print(
        "then click Allow. (If Google says the app is unverified: Advanced -> Go to ... (unsafe).)\n",
        flush=True,
    )

    return flow.run_local_server(
        port=port or 8080,
        prompt="consent",
        access_type="offline",
        state="bks_oauth_2026",
        authorization_prompt_message=_UrlCapturer(),
        success_message="Done — YouTube channel connect ho chuka hai! Aap is window ko band kar sakte hain.",
    )


def verify(creds) -> dict:
    """Prove the token works: a real API call, not a JSON guess."""
    from googleapiclient.discovery import build

    api = build("youtube", "v3", credentials=creds, cache_discovery=False)
    res = api.channels().list(part="snippet,statistics", mine=True).execute()
    items = res.get("items") or []
    if not items:
        raise SystemExit(
            "Token works but this account has no channel — sign in with the channel's own account."
        )
    ch = items[0]
    return {
        "channel": ch["snippet"]["title"],
        "id": ch["id"],
        "subscribers": ch.get("statistics", {}).get("subscriberCount", "?"),
        "videos": ch.get("statistics", {}).get("videoCount", "?"),
    }


def set_github_secret(name: str, value: str, token: str) -> None:
    """Seal the secret with the repo's public key and PUT it — the documented GitHub flow."""
    import base64

    import requests
    from nacl import encoding, public

    h = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=h, timeout=30
    )
    if r.status_code != 200:
        raise SystemExit(
            f"GitHub public key failed ({r.status_code}) — token needs `secrets: write`."
        )
    key_id, key_b64 = r.json()["key_id"], r.json()["key"]
    sealed = public.SealedBox(public.PublicKey(key_b64.encode(), encoding.Base64Encoder()))
    encrypted = base64.b64encode(sealed.encrypt(value.encode())).decode()
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
        headers=h,
        json={"encrypted_value": encrypted, "key_id": key_id},
        timeout=30,
    )
    if r.status_code not in (201, 204):
        raise SystemExit(f"GitHub secret update failed: {r.status_code} {r.text[:200]}")
    print(f"✓ {name} updated on GitHub ({REPO})")


def main() -> int:
    ap = argparse.ArgumentParser(prog="one_click_auth")
    ap.add_argument(
        "--secret", default="client_secret.json", help="OAuth client JSON (Desktop app)"
    )
    ap.add_argument("--port", type=int, default=0, help="local port (0 = pick a free one)")
    ap.add_argument(
        "--set-github-secret",
        action="store_true",
        help="also update the YOUTUBE_TOKEN_JSON secret (needs GH_TOKEN env)",
    )
    a = ap.parse_args()

    secret = Path(a.secret)
    if not secret.exists():
        return print(f"\n✗ {secret} not found in {ROOT}.") or 1

    try:
        creds = authorize(secret, a.port)
    except Exception as exc:
        return print(f"\n✗ Authorization failed: {exc}") or 1

    token_json = creds.to_json()
    if not json.loads(token_json).get("refresh_token"):
        return (
            print(
                "\n✗ Google returned no refresh_token. Remove the app's access at "
                "myaccount.google.com/permissions and run again with prompt=consent."
            )
            or 1
        )

    try:
        info = verify(creds)
    except SystemExit as exc:
        return print(f"\n✗ {exc}") or 1
    except Exception as exc:
        return print(f"\n✗ Token could not reach YouTube: {exc}") or 1

    out = Path("token.json")
    out.write_text(token_json, encoding="utf-8")
    print(
        f"\n✓ VERIFIED — channel: {info['channel']}  (id {info['id']}), "
        f"subs {info['subscribers']}, videos {info['videos']}"
    )
    print(f"✓ written to {out.resolve()}  (git-ignored — never commit it)")

    gh = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if gh:
        try:
            set_github_secret("YOUTUBE_TOKEN_JSON", token_json, gh)
            # Also ensure client secret is present
            if Path("client_secret.json").exists():
                set_github_secret("YOUTUBE_CLIENT_SECRET_JSON", Path("client_secret.json").read_text(encoding="utf-8"), gh)
            print("✓ GitHub Secrets updated automatically!")
        except Exception as exc:
            print(f"! GitHub secret update error: {exc}")
    else:
        print("! GITHUB_TOKEN not found in .env — skipping the GitHub update.")

    print("\n===== YOUTUBE_TOKEN_JSON =====\n")
    print(token_json)
    print("\n" + "=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
