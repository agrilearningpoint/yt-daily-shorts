"""Direct exchange of YouTube OAuth code or URL into token.json & GitHub Secrets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from scripts.one_click_auth import verify, set_github_secret

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def client() -> dict:
    cfg = json.loads(Path("client_secret.json").read_text(encoding="utf-8"))
    return cfg.get("installed") or cfg.get("web") or cfg


def verifier_for(secret: str) -> str:
    return hashlib.sha256(("yt-daily-shorts-pkce:" + secret).encode()).hexdigest()


def extract_code(raw: str) -> tuple[str, str]:
    """Returns (code, redirect_uri_used)."""
    raw = (raw or "").strip()
    redirect_uri = "http://localhost"
    if raw.startswith("http"):
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [""])[0]
        # determine redirect_uri from the URL
        if parsed.port:
            redirect_uri = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            if parsed.path and parsed.path != "/":
                redirect_uri += parsed.path
        return code, redirect_uri
    if "code=" in raw:
        qs = urllib.parse.parse_qs(raw.split("?", 1)[-1])
        return qs.get("code", [""])[0], redirect_uri
    return raw, redirect_uri


def exchange(code: str, redirect_uri: str = "http://localhost"):
    from google_auth_oauthlib.flow import Flow

    c = client()
    # Try with exact redirect_uri, then fallback to http://localhost and http://localhost/
    uris_to_try = [redirect_uri]
    for alt in ["http://localhost", "http://localhost/", "http://localhost:8080", "http://localhost:8080/"]:
        if alt not in uris_to_try:
            uris_to_try.append(alt)

    last_exc = None
    for uri in uris_to_try:
        try:
            flow = Flow.from_client_config(
                {"installed": c},
                SCOPES,
                redirect_uri=uri,
                code_verifier=verifier_for(c["client_secret"]),
                autogenerate_code_verifier=False,
            )
            flow.fetch_token(code=code)
            return flow.credentials
        except Exception as e:
            last_exc = e

    raise last_exc


def main():
    ap = argparse.ArgumentParser(description="Exchange OAuth code for YouTube Token")
    ap.add_argument("raw", nargs="?", help="OAuth code or redirected URL")
    a = ap.parse_args()

    raw = a.raw
    if not raw:
        if sys.stdin.isatty():
            raw = input("Paste redirected URL or code: ").strip()
        else:
            raw = sys.stdin.read().strip()

    if not raw:
        print("✗ No code provided.")
        return 1

    code, redirect_uri = extract_code(raw)
    if not code:
        print("✗ Could not extract code from input.")
        return 1

    print(f"Exchanging code (using redirect_uri: {redirect_uri})...")
    try:
        creds = exchange(code, redirect_uri)
    except Exception as exc:
        print(f"✗ Token exchange failed: {exc}")
        return 1

    token_json = creds.to_json()
    if not json.loads(token_json).get("refresh_token"):
        print("✗ Google did not return a refresh_token. Revoke old access and try again with prompt=consent.")
        return 1

    try:
        info = verify(creds)
    except Exception as exc:
        print(f"✗ YouTube API verification failed: {exc}")
        return 1

    # Save locally
    Path("token.json").write_text(token_json, encoding="utf-8")
    print(
        f"\n✓ VERIFIED — Channel: {info['channel']} (ID: {info['id']}), "
        f"Subs: {info['subscribers']}, Videos: {info['videos']}"
    )
    print("✓ Saved to token.json")

    # Update GitHub Secrets
    gh = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if gh:
        try:
            set_github_secret("YOUTUBE_TOKEN_JSON", token_json, gh)
            if Path("client_secret.json").exists():
                set_github_secret(
                    "YOUTUBE_CLIENT_SECRET_JSON",
                    Path("client_secret.json").read_text(encoding="utf-8"),
                    gh,
                )
            print("✓ GitHub Secrets YOUTUBE_TOKEN_JSON and YOUTUBE_CLIENT_SECRET_JSON updated successfully!")
        except Exception as exc:
            print(f"! Error updating GitHub secrets: {exc}")
    else:
        print("! GITHUB_TOKEN not set, skipped GitHub secret update.")

    print("\n✓ ALL COMPLETE! YouTube authentication is fully active and ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
