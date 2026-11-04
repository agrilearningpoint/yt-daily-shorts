"""Check GitHub Actions workflows and run statuses via GitHub REST API."""

import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO = os.getenv("GITHUB_REPOSITORY", "agrilearningpoint/yt-daily-shorts")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "YTDailyShorts-WorkflowChecker/1.0"
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def check_workflows():
    print("=" * 65)
    print(f"[CHECK] Checking GitHub Actions for: {REPO}")
    print("=" * 65)

    # 1. List Workflows
    wf_url = f"https://api.github.com/repos/{REPO}/actions/workflows"
    try:
        r = requests.get(wf_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            workflows = data.get("workflows", [])
            print(f"\nRegistered Workflows ({len(workflows)}):")
            for wf in workflows:
                state_badge = "[ACTIVE]" if wf.get("state") == "active" else "[INACTIVE]"
                print(f"  * {wf.get('name')} {state_badge}")
                print(f"    Path: {wf.get('path')} (ID: {wf.get('id')})")
        else:
            print(f"Failed fetching workflows: HTTP {r.status_code} - {r.text[:200]}")
    except Exception as e:
        print(f"Error fetching workflows: {e}")

    # 2. List Recent Runs
    runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=5"
    try:
        r = requests.get(runs_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            runs = data.get("workflow_runs", [])
            print(f"\nRecent Workflow Runs ({len(runs)}):")
            if not runs:
                print("  (No workflow runs yet. Workflows will trigger on schedule or manual dispatch).")
            for run in runs:
                status = run.get("status", "unknown")
                conclusion = run.get("conclusion") or "running"
                badge = "[SUCCESS]" if conclusion == "success" else (f"[{conclusion.upper()}]")
                print(f"  {badge} Run #{run.get('run_number')}: {run.get('name')}")
                print(f"    Status: {status} | Conclusion: {conclusion} | Event: {run.get('event')}")
                print(f"    URL: {run.get('html_url')}")
        else:
            print(f"Failed fetching runs: HTTP {r.status_code} - {r.text[:200]}")
    except Exception as e:
        print(f"Error fetching runs: {e}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    check_workflows()
