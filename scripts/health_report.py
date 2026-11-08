"""Daily health check + weekly performance report, sent to Telegram.

daily : today's news Short is on the channel? YouTube token still refreshes? LLM providers alive?
weekly: views / likes / comments of the last 7 uploads, best and worst video.
Exit code 1 when something needs the owner's attention (so the workflow shows red).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from youtube.oauth import YouTubeOAuthManager  # noqa: E402
from youtube.uploader import find_existing_upload, publish_key  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def telegram(text: str) -> None:
    t, c = os.getenv("YT_TELEGRAM_BOT_TOKEN"), os.getenv("YT_TELEGRAM_CHAT_ID")
    print(text)
    if t and c:
        try:
            requests.post(f"https://api.telegram.org/bot{t}/sendMessage",
                          json={"chat_id": c, "text": text, "disable_web_page_preview": True}, timeout=15)
        except Exception as exc:
            print("telegram failed:", exc)


def youtube():
    oauth = YouTubeOAuthManager(os.getenv("YT_YOUTUBE_CLIENT_SECRET_JSON", ""), os.getenv("YT_YOUTUBE_TOKEN_JSON", ""))
    creds = oauth.get_credentials()
    if not creds:
        return None, oauth.last_error or "no credentials"
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds, cache_discovery=False), ""


def llm_alive() -> list:
    out = []
    key = os.getenv("YT_GEMINI_API_KEY", "")
    if key:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key}, timeout=20)
        out.append(("Gemini", r.ok))
    key = os.getenv("YT_GROQ_API_KEY", "")
    if key:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        out.append(("Groq", r.ok))
    key = os.getenv("YT_OPENROUTER_API_KEY", "")
    if key:
        r = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        out.append(("OpenRouter", r.ok))
    return out


def daily() -> int:
    problems, lines = [], []
    yt, err = youtube()
    today = datetime.now(IST)
    if not yt:
        problems.append(f"YouTube login FAILED ({err[:120]}). Re-authorise the channel token.")
    else:
        key = publish_key("news", today)
        vid = find_existing_upload(yt, key)
        if vid:
            lines.append(f"✅ Today's news Short is live: https://youtube.com/shorts/{vid}")
        else:
            problems.append(f"No news Short uploaded today ({key}). Check the 05:30 run.")
    for name, ok in llm_alive():
        lines.append(f"{'✅' if ok else '❌'} {name} API")
        if not ok:
            problems.append(f"{name} API key not working")
    head = "🩺 BHARAT KI SOCH daily health " + today.strftime("%d %b %Y")
    body = "\n".join(lines + [f"⚠️ {p}" for p in problems]) or "all good"
    telegram(f"{head}\n{body}")
    return 1 if problems else 0


def weekly() -> int:
    yt, err = youtube()
    if not yt:
        telegram(f"📊 Weekly report failed: YouTube login ({err[:120]})")
        return 1
    ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=15).execute()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])
           if datetime.fromisoformat(i["contentDetails"].get("videoPublishedAt", "1970-01-01T00:00:00Z")
                                     .replace("Z", "+00:00")) >= since]
    if not ids:
        telegram("📊 Weekly report: no uploads in the last 7 days")
        return 1
    vids = yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute().get("items", [])
    rows = []
    for v in vids:
        st = v.get("statistics", {})
        rows.append((int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), int(st.get("commentCount", 0)),
                     v["snippet"]["title"][:60], v["id"]))
    rows.sort(reverse=True)
    tv, tl, tc = (sum(r[i] for r in rows) for i in range(3))
    subs = ch.get("statistics", {}).get("subscriberCount", "?")
    text = [f"📊 BHARAT KI SOCH weekly report", f"{len(rows)} videos | {tv} views | {tl} likes | {tc} comments | "
            f"{subs} subscribers",
            f"🏆 Best: {rows[0][3]} ({rows[0][0]} views) https://youtube.com/shorts/{rows[0][4]}",
            f"🔻 Lowest: {rows[-1][3]} ({rows[-1][0]} views)"]
    telegram("\n".join(text))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["daily", "weekly"])
    sys.exit(daily() if ap.parse_args().mode == "daily" else weekly())
