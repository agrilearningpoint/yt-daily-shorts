"""Make sure today's BHARAT KI SOCH news Short is uploaded by 08:00 IST.

Run with shell credentials provider github-pat. Prints one status line:
  DONE <url>          today's video already uploaded
  RUNNING <run_id>    a live run is queued/in progress
  DISPATCHED          started a new live run
  FAILED_DISPATCH ... could not start a run
"""
import datetime as dt
import json
import re
import sys
import urllib.request

REPO = "agrilearningpoint/yt-daily-shorts"
API = f"https://api.github.com/repos/{REPO}"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if raw else json.loads(data)


def run_log(run_id):
    jobs = get(f"{API}/actions/runs/{run_id}/jobs")["jobs"]
    out = ""
    for j in jobs:
        try:
            out += get(f"{API}/actions/jobs/{j['id']}/logs", raw=True).decode("utf-8", "ignore")
        except Exception:
            pass
    return out


def main():
    today = dt.datetime.now(IST).date()
    runs = get(f"{API}/actions/workflows/daily_shorts.yml/runs?per_page=15")["workflow_runs"]
    for r in runs:
        created = dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone(IST).date()
        if created != today or (r.get("display_title") or "").startswith("dry-run"):
            continue
        if r["status"] != "completed":
            print(f"RUNNING {r['id']}")
            return
        if r["conclusion"] == "success":
            log = run_log(r["id"])
            m = re.search(r"done: (https://youtube\.com/shorts/\S+)", log)
            if m:
                print(f"DONE {m.group(1)}")
                return
            if re.search(r"already uploaded|duplicate", log, re.I):
                print("DONE (duplicate guard: today's video already on channel)")
                return
    body = json.dumps({"ref": "main", "inputs": {"video_type": "news", "dry_run": "false"}}).encode()
    req = urllib.request.Request(f"{API}/actions/workflows/daily_shorts.yml/dispatches", data=body, method="POST",
                                 headers={"Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print("DISPATCHED" if r.status == 204 else f"FAILED_DISPATCH {r.status}")
    except Exception as exc:
        print(f"FAILED_DISPATCH {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
