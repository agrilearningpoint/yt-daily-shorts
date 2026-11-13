"""A tiny self-hosted OAuth station: sign in once, everything else is automatic.

    python scripts/oauth_relay.py --port 8080 [--set-github-secret --run-after]

Flow (the only manual step is Google's own consent screen):
  1. You open this page and press "Google से जोड़ें".
  2. Google asks for permission; it then redirects to http://localhost:PORT/... which does not
     load on your machine (no listener there). You copy that one address back into this page.
  3. The server exchanges the code (PKCE, same verifier), verifies it with a real channels.list
     call, writes token.json, updates the YOUTUBE_TOKEN_JSON GitHub secret and can start an
     unlisted upload immediately. Nothing is ever printed to a chat.

Why the localhost hop: desktop OAuth clients only accept http://localhost redirects, so the
code has to come back from your browser. Everything after that is handled here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
REPO = "agrilearningpoint/yt-daily-shorts"
STATE: dict = {"state": "", "result": None, "error": "", "log": []}


def note(msg: str) -> None:
    STATE["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")
    print(msg, flush=True)


def client() -> dict:
    cfg = json.loads(Path("client_secret.json").read_text(encoding="utf-8"))
    return cfg.get("installed") or cfg.get("web") or cfg


def verifier_for(secret: str) -> str:
    # deterministic, so the same PKCE pair works before and after the redirect
    return hashlib.sha256(("yt-daily-shorts-pkce:" + secret).encode()).hexdigest()


def auth_url(port: int) -> str:
    c = client()
    verifier = verifier_for(c["client_secret"])
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    q = {
        "client_id": c["client_id"],
        "redirect_uri": f"http://localhost:{port}/oauth/callback",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": STATE["state"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(q)


def extract_code(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("http"):
        return urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [""])[0]
    if "code=" in raw:
        return urllib.parse.parse_qs(raw.split("?", 1)[-1]).get("code", [""])[0]
    return raw


def exchange(code: str, port: int):
    from google_auth_oauthlib.flow import Flow

    c = client()
    flow = Flow.from_client_config({"installed": c}, SCOPES,
                                   redirect_uri=f"http://localhost:{port}/oauth/callback",
                                   code_verifier=verifier_for(c["client_secret"]),
                                   autogenerate_code_verifier=False)
    flow.fetch_token(code=code)
    return flow.credentials


def verify(creds) -> dict:
    from googleapiclient.discovery import build

    api = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = (api.channels().list(part="snippet,statistics", mine=True).execute().get("items") or [])
    if not items:
        raise RuntimeError("इस account का कोई YouTube channel नहीं मिला — channel वाले account से sign in करें")
    ch = items[0]
    return {"channel": ch["snippet"]["title"], "id": ch["id"],
            "subs": ch.get("statistics", {}).get("subscriberCount", "?"),
            "videos": ch.get("statistics", {}).get("videoCount", "?")}


def set_github_secret(name: str, value: str) -> None:
    import requests
    from nacl import encoding, public

    token = os.environ.get("GH_TOKEN", "").strip() or Path("/home/user/.secrets/github_token").read_text().strip()
    h = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=h, timeout=30)
    r.raise_for_status()
    sealed = public.SealedBox(public.PublicKey(r.json()["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(sealed.encrypt(value.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{REPO}/actions/secrets/{name}", headers=h,
                     json={"encrypted_value": enc, "key_id": r.json()["key_id"]}, timeout=30)
    r.raise_for_status()


PAGE = """<!doctype html><html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>YouTube जोड़ें</title>
<style>
 body{{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#0b0f16;color:#e8eaf0;
      display:flex;justify-content:center;padding:28px 16px}}
 .card{{max-width:640px;width:100%;background:#141a24;border:1px solid #24303f;border-radius:16px;padding:26px}}
 h1{{font-size:21px;margin:0 0 6px}} p{{color:#a9b4c4;line-height:1.6;font-size:15px}}
 .step{{background:#0f1520;border:1px solid #223041;border-radius:12px;padding:16px;margin:14px 0}}
 .n{{display:inline-block;background:#d4af37;color:#111;font-weight:700;border-radius:20px;padding:1px 10px;font-size:13px;margin-right:8px}}
 a.btn,button{{display:inline-block;background:#d4af37;color:#111;font-weight:700;border:0;border-radius:10px;
      padding:12px 18px;font-size:15px;cursor:pointer;text-decoration:none;margin-top:10px}}
 input{{width:100%;box-sizing:border-box;background:#0b1119;border:1px solid #2b3a4d;color:#e8eaf0;border-radius:10px;
      padding:12px;font-size:14px;margin-top:10px}}
 .ok{{color:#4ade80;font-weight:600}} .bad{{color:#f87171;font-weight:600}}
 code{{background:#0b1119;padding:2px 6px;border-radius:6px;color:#c7d2fe;font-size:13px}}
 .log{{font-family:ui-monospace,monospace;font-size:12px;color:#8b98aa;white-space:pre-wrap;margin-top:12px}}
</style></head><body><div class="card">
<h1>YouTube channel जोड़ें</h1>
<p>एक बार Google में Allow दबाना है — बाक़ी सब यह server खुद करेगा (token verify → GitHub secret → upload).</p>
{body}
<div class="log">{log}</div>
</div></body></html>"""

STEP1 = """<div class="step"><span class="n">1</span><b>Google से जोड़ें</b>
 <p>नीचे वाले button से sign in करें — वही account जो channel का owner है।</p>
 <a class="btn" href="/start">Google से जोड़ें →</a></div>
<div class="step"><span class="n">2</span><b>लौटा हुआ address paste करें</b>
 <p>Allow के बाद browser <code>http://localhost:{port}/oauth/callback?code=…</code> पर जाएगा जो खुलेगा नहीं —
 वही address bar का पूरा link नीचे paste करें। (code अकेला भी चलेगा।)</p>
 <form method="post" action="/finish"><input name="code" placeholder="http://localhost:{port}/oauth/callback?code=4/0A…"
   autocomplete="off"><button type="submit">जोड़ें और verify करें</button></form></div>"""

DONE = """<div class="step"><span class="n">✓</span><b class="ok">{channel}</b>
 <p>Token verify हो गया (channel id <code>{cid}</code>, {subs} subscribers, {videos} videos).</p>
 <p>GitHub secret <code>YOUTUBE_TOKEN_JSON</code>: {secret}</p>
 <p>{run}</p></div>"""


def render(body: str) -> bytes:
    log = "\n".join(html.escape(x) for x in STATE["log"][-14:])
    return PAGE.format(body=body, log=log).encode()


class Handler(BaseHTTPRequestHandler):
    port = 8080

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/start":
            STATE["state"] = secrets.token_urlsafe(16)
            STATE["error"] = ""
            self.send_response(302)
            self.send_header("Location", auth_url(self.port))
            self.end_headers()
            return
        if path == "/status":
            self._send(200, json.dumps(STATE, ensure_ascii=False).encode(), "application/json")
            return
        if path in ("/", "/index.html"):
            if STATE["result"]:
                r = STATE["result"]
                self._send(200, render(DONE.format(channel=html.escape(r["channel"]), cid=r["id"],
                                                   subs=r["subs"], videos=r["videos"],
                                                   secret=r.get("secret", "—"), run=r.get("run", ""))))
            else:
                self._send(200, render(STEP1.format(port=self.port) +
                                       (f'<p class="bad">{html.escape(STATE["error"])}</p>' if STATE["error"] else "")))
            return
        self._send(404, b"not found")

    def do_POST(self) -> None:  # noqa: N802
        if urllib.parse.urlparse(self.path).path != "/finish":
            return self._send(404, b"not found")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        code = extract_code(urllib.parse.parse_qs(raw).get("code", [""])[0])
        if not code:
            STATE["error"] = "code खाली है — address bar का पूरा link paste करें।"
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        try:
            note("code मिला — token exchange हो रहा है")
            creds = exchange(code, self.port)
            token_json = creds.to_json()
            if not json.loads(token_json).get("refresh_token"):
                raise RuntimeError("Google ने refresh_token नहीं दिया — myaccount.google.com/permissions से "
                                   "पुराना access हटाकर दोबारा try करें")
            info = verify(creds)
            note(f"verified: {info['channel']} ({info['id']})")
            Path("token.json").write_text(token_json, encoding="utf-8")
            os.chmod("token.json", 0o600)
            secret_msg = "update नहीं हुआ"
            try:
                set_github_secret("YOUTUBE_TOKEN_JSON", token_json)
                secret_msg = "✓ update हो गया"
                note("GitHub secret YOUTUBE_TOKEN_JSON updated")
            except Exception as exc:
                secret_msg = f"असफल ({exc}) — token.json बन गया है"
                note(f"GitHub secret failed: {exc}")
            STATE["result"] = {**info, "secret": secret_msg, "run": ""}
            note("तैयार — अब upload चलाया जा सकता है")
        except Exception as exc:
            STATE["error"] = f"{exc}"
            note(f"error: {exc}")
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter access log
        return


def main() -> int:
    ap = argparse.ArgumentParser(prog="oauth_relay")
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    Handler.port = a.port
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    note(f"listening on 0.0.0.0:{a.port}")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
