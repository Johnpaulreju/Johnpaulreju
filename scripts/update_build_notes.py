"""Refresh the three monthly profile highlights and their public source archive."""

import calendar
from collections import Counter
from datetime import date, timedelta
from html import escape
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "build-notes"
ACTIVITY = ARCHIVE / "activity"
LOGIN = "Johnpaulreju"
PROFILE = f"https://github.com/{LOGIN}/{LOGIN}"
RAW = f"https://raw.githubusercontent.com/{LOGIN}/{LOGIN}/main/build-notes/activity"
START = "<!-- monthly-builds:start -->"
END = "<!-- monthly-builds:end -->"


def shift_month(month, offset):
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def replace_section(document, body):
    if document.count(START) != 1 or document.count(END) != 1:
        raise ValueError("Expected one marked monthly build section")
    before, rest = document.split(START)
    _, after = rest.split(END)
    return before + START + "\n\n" + body.strip() + "\n\n" + END + after


def search(kind, first, last):
    filters = ("is:pr created:" if kind == "issues" else "merge:false author-date:")
    query = f"author:{LOGIN} is:public {filters}{first}..{last}"
    results = []
    for page in range(1, 11):
        command = ["gh", "api", "-X", "GET", f"search/{kind}", "-f", f"q={query}",
                   "-f", "sort=" + ("created" if kind == "issues" else "author-date"),
                   "-f", "order=desc", "-F", "per_page=100", "-F", f"page={page}"]
        for attempt in range(3):
            try:
                record = json.loads(subprocess.check_output(command))
                if record.get("incomplete_results") or "items" not in record:
                    raise ValueError("Incomplete GitHub search results")
                break
            except (subprocess.CalledProcessError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(10 * (attempt + 1))
        if record["total_count"] > 1000:
            if first == last:
                raise ValueError(f"Search limit reached on {first}")
            middle = first + (last - first) // 2
            return search(kind, first, middle) + search(kind, middle + timedelta(days=1), last)
        results.extend(record["items"])
        if len(record["items"]) < 100 or len(results) >= record["total_count"]:
            break
    return results


def monthly_items(month):
    last = shift_month(month, 1) - timedelta(days=1)
    entries = {}
    for kind in ("commits", "issues"):
        for item in search(kind, month, last):
            url = item["html_url"]
            if kind == "commits":
                if item["repository"]["private"] or (item["author"] or {}).get("login", "").lower() != LOGIN.lower():
                    continue
                stamp = item["commit"]["author"]["date"]
                title = item["commit"]["message"]
                label = "Commit"
            else:
                if item["user"]["login"].lower() != LOGIN.lower() or "pull_request" not in item:
                    continue
                stamp = item["created_at"]
                title = item["title"]
                label = f"PR #{item['number']}"
            match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(?:commit/[a-f0-9]{40}|pull/[0-9]+)", url)
            if not match:
                raise ValueError("Unexpected GitHub evidence URL")
            entries[url] = (stamp[:10], label, match[1], title.splitlines()[0], url)
    return sorted(entries.values(), key=lambda item: (item[0], item[4]), reverse=True)


def safe_text(title):
    # User-authored subjects may contain arbitrary Markdown or HTML.
    title = " ".join("".join(ch for ch in title if ch.isprintable()).split())
    if len(title) > 142:
        title = title[:139].rsplit(" ", 1)[0] + "…"
    return re.sub(r"([\\\[\]_*\x60~|!])", r"\\\1", escape(title)).replace("@", "@\u200b")


def editorial_titles(notes):
    titles = {}
    for line in notes.splitlines():
        label = re.search(r"\*\*[A-Z][a-z]{2} \d+ · (.*?)\.?\*\*", line)
        if label:
            for url in re.findall(r"https://github\.com/[\w.-]+/[\w.-]+/(?:commit/[a-f0-9]{40}|pull/\d+)", line):
                titles[url] = label[1]
    return titles


def highlights(entries, titles, current):
    # Give a new, descriptive change in the current month a chance to displace
    # an older curated pick. Older months keep their editorial highlights.
    last_curated = max((row[0] for row in entries if row[4] in titles), default="")
    selected = []
    remaining = entries[:]
    while remaining and len(selected) < 2:
        def priority(item):
            day, label, repo, subject, url = item
            readable = len(subject.split()) >= 4
            return (repo.lower() != f"{LOGIN}/{LOGIN}".lower(),
                    current and day > last_curated and readable,
                    url in titles, readable,
                    all(repo != row[2] for row in selected),
                    bool(selected) and label.startswith("PR"), day)
        pick = max(remaining, key=priority)
        selected.append(pick)
        title = titles.get(pick[4], pick[3]).casefold()
        remaining = [row for row in remaining if titles.get(row[4], row[3]).casefold() != title]
    return selected


def sparkline(month, entries, today):
    name = month.strftime("%B %Y")
    count = Counter(int(row[0][-2:]) for row in entries)
    length = calendar.monthrange(month.year, month.month)[1]
    baseline = 21
    height = max(count.values(), default=1)
    points = [f"{2 + (day - 1) * 128 / (length - 1):.1f},{baseline - 16 * count[day] / height:.1f}"
              for day in range(1, min(length, (today - month).days + 1) + 1)]
    path = "M" + " L".join(points)
    tracer = '<use href="#days" class="tracer"/>' if entries else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="132" height="26" viewBox="0 0 132 26" role="img" aria-labelledby="title">
  <title id="title">Daily public commits and pull requests in {name}</title>
  <style>
    svg {{ --line:#8250df; --trace:#5424a9 }}
    @media (prefers-color-scheme:dark) {{ svg {{ --line:#b899f5; --trace:#f2eaff }} }}
    use {{ fill:none; stroke:var(--line); stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round }}
    .tracer {{ stroke:var(--trace); stroke-dasharray:10 110; animation:pass 6s ease-in-out infinite }}
    @keyframes pass {{ 0% {{ stroke-dashoffset:10 }} 75%,100% {{ stroke-dashoffset:-100 }} }}
    @media (prefers-reduced-motion:reduce) {{ .tracer {{ display:none; animation:none }} }}
  </style>
  <defs><path id="days" pathLength="100" d="{path}"/></defs>
  <use href="#days"/>{tracer}
</svg>
"""


def search_links(month):
    last = shift_month(month, 1) - timedelta(days=1)
    base = f"author:{LOGIN} is:public"
    commits = urlencode({"q": f"{base} merge:false author-date:{month}..{last}", "type": "commits"})
    pulls = urlencode({"q": f"{base} is:pr created:{month}..{last}", "type": "pullrequests"})
    return f"[Search commits](https://github.com/search?{commits}) · [Search pull requests](https://github.com/search?{pulls})"


def entry_line(item, titles, include_date=False):
    day, label, repo, title, url = item
    readable = safe_text(titles.get(url, title)) or "Untitled change"
    prefix = f"{day[5:]} · " if include_date else ""
    return f"- {prefix}[{readable}]({url}) · {safe_text(repo.split('/')[1])} · {label}"


def refresh(today):
    current = today.replace(day=1)
    earliest = shift_month(current, -2)
    existing = {p.stem for p in ACTIVITY.glob("????-??.md")}
    backfill = min(earliest, date.fromisoformat(max(existing) + "-01")) if existing else earliest
    pages, visible = {}, []
    archive_text = (ARCHIVE / "README.md").read_text()
    curated = editorial_titles(archive_text)
    month = current
    while month >= backfill:
        slug = month.strftime("%Y-%m")
        title = month.strftime("%B %Y")
        entries = monthly_items(month)
        empty = "No public authored commits or pull requests were found for this month."
        evidence = "\n".join(entry_line(entry, curated, True) for entry in entries) or empty
        pages[ACTIVITY / f"{slug}.md"] = f"# {title}\n\n{search_links(month)}\n\n{evidence}\n"
        if month >= earliest:
            cards = "\n".join(entry_line(row, curated) for row in highlights(entries, curated, month == current)) or empty
            pages[ACTIVITY / f"{slug}.svg"] = sparkline(month, entries, today)
            detail = f"{PROFILE}/blob/main/build-notes/activity/{slug}.md"
            visible.append(f'### [{title}]({detail})&ensp;<img src="{RAW}/{slug}.svg" width="106" height="21" alt="">\n\n{cards}')
        existing.add(slug)
        month = shift_month(month, -1)
    profile_section = ("## What I built each month\n\nSelect a change to see the code. The small charts show daily public commits and pull requests.\n\n"
                       + "\n\n".join(visible)
                       + f"\n\n[Browse the monthly archive]({PROFILE}/tree/main/build-notes#what-i-built-each-month)")
    index_rows = []
    for year in sorted({name[:4] for name in existing}, reverse=True):
        links = [f"[{calendar.month_abbr[int(name[5:])]}](./activity/{name}.md)"
                 for name in sorted(existing, reverse=True) if name.startswith(year)]
        index_rows.append(f"**{year}** · " + " · ".join(links))
    pages[ARCHIVE / "README.md"] = replace_section(archive_text, "\n\n".join(index_rows))
    profile = ROOT / "README.md"
    pages[profile] = replace_section(profile.read_text(), profile_section)
    ACTIVITY.mkdir(exist_ok=True)
    for filename, content in pages.items():
        filename.write_text(content)
    # Old evidence pages remain available after their chart leaves the profile.
    for chart in ACTIVITY.glob("????-??.svg"):
        if chart.stem < earliest.strftime("%Y-%m"):
            chart.unlink()


if __name__ == "__main__":
    from datetime import datetime, timezone
    refresh(datetime.now(timezone.utc).date())
