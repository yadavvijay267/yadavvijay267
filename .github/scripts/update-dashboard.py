#!/usr/bin/env python3
"""Auto-update the stats in id-dashboard.svg (public repos + total commits + month).

Runs in GitHub Actions (daily) with GITHUB_TOKEN. Fetches live counts from the
GitHub API, regenerates the odometer strips in id-dashboard.svg, updates the
month label, and rewrites the file only when something changed. Exits non-zero
on API failure so a bad run is visible instead of silently committing stale data.

Usage:
    python3 update-dashboard.py [path/to/id-dashboard.svg]
    Env: GITHUB_TOKEN (optional locally; provided in Actions),
         GITHUB_USERNAME (default: yadavvijay267)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "yadavvijay267")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def api_get(url):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "dashboard-updater"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers


def list_repos(username):
    repos, url = [], f"{API}/users/{username}/repos?per_page=100"
    while url:
        data, headers = api_get(url)
        repos.extend(r["name"] for r in data)
        nxt = re.search(r'<([^>]+)>; rel="next"', headers.get("Link", "") or "")
        url = nxt.group(1) if nxt else None
    return repos


def count_commits(username, repo):
    url = f"{API}/repos/{username}/{repo}/commits?per_page=1"
    try:
        data, headers = api_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 409:  # empty repository
            return 0
        raise
    m = re.search(r'page=(\d+)>; rel="last"', headers.get("Link", "") or "")
    return int(m.group(1)) if m else len(data)


def regen_strip(svg, x, new_max):
    """Replace the odometer strip at x with numbers 0..new_max (36px apart from y=184)."""
    pat = re.compile(
        r'<text x="%d" y="\d+" font-family="Space Grotesk, sans-serif" '
        r'font-size="30" font-weight="700" fill="#f5f7fb">\d+</text>' % x)
    matches = list(pat.finditer(svg))
    if not matches:
        raise SystemExit(f"strip at x={x} not found - SVG structure changed?")
    vals = [int(re.search(r'>(\d+)</text>$', m.group(0)).group(1)) for m in matches]
    if vals != list(range(len(vals))):
        raise SystemExit(f"strip at x={x} is not sequential 0..n: {vals}")
    old_max = len(vals) - 1
    if old_max == new_max:
        return svg, False
    new_texts = "".join(
        f'<text x="{x}" y="{184 + 36 * k}" font-family="Space Grotesk, sans-serif" '
        f'font-size="30" font-weight="700" fill="#f5f7fb">{k}</text>'
        for k in range(new_max + 1))
    svg = svg[:matches[0].start()] + new_texts + svg[matches[-1].end():]
    old_travel, new_travel = -36 * old_max, -36 * new_max
    for old, new in [(f"translate(0 {old_travel})", f"translate(0 {new_travel})"),
                     (f'values="0 0; 0 0; 0 {old_travel}"',
                      f'values="0 0; 0 0; 0 {new_travel}"')]:
        if svg.count(old) != 1:
            raise SystemExit(f"expected exactly one {old!r}, found {svg.count(old)}")
        svg = svg.replace(old, new)
    return svg, True


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "id-dashboard.svg"
    with open(path, encoding="utf-8") as f:
        svg = f.read()

    repos = list_repos(USERNAME)
    total_commits = sum(count_commits(USERNAME, r) for r in repos)
    now = datetime.now(timezone.utc)
    month_label = f"LIVE · {MONTHS[now.month - 1]} {now.year}"

    svg, c1 = regen_strip(svg, 318, len(repos))     # PUBLIC REPOS
    svg, c2 = regen_strip(svg, 518, total_commits)  # TOTAL COMMITS
    changed = c1 or c2
    m = re.search(r"LIVE · [A-Z]{3} \d{4}", svg)
    if m and m.group(0) != month_label:
        svg = svg.replace(m.group(0), month_label, 1)
        changed = True

    print(f"repos={len(repos)} commits={total_commits} month={month_label} changed={changed}")
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
