"""Convenience developer runner for local dry-run testing."""

import subprocess
import sys

def main():
    print("=" * 60)
    print("▶️ Running YT Daily Shorts in Local Dry-Run Mode...")
    print("=" * 60)
    cmd = [sys.executable, "main.py", "--video-type", "all", "--dry-run"]
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
