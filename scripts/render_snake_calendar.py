"""Frame Platane's generated route using the matching public GitHub calendar."""

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from render_snake_preview import SVG, draw


THEMES = {
    "dark": ("#0d1117", "#f0f6fc", "#9198a1", "#3d444d",
             ["#151b23", "#033a16", "#196c2e", "#2ea043", "#56d364"]),
    "light": ("#ffffff", "#1f2328", "#59636e", "#d1d9e0",
              ["#eff2f5", "#aceebb", "#4ac26b", "#2da44e", "#116329"]),
}


LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")


def render(source, destination, theme, calendar):
    total = calendar["totalContributions"]
    heading = f"{total:,} contribution{'s' if total != 1 else ''} in the last year"
    positions = {
        (column, day["weekday"]): day
        for column, week in enumerate(calendar["weeks"])
        for day in week["contributionDays"]
    }
    original = ET.parse(source).getroot()
    css = original.find(f"{{{SVG}}}style").text
    levels = dict(re.findall(r"\.c\.(c\w+)\{fill:var\(--c(\d+)\)", css))
    days = {}
    snake = []
    for rect in original.findall(f"{{{SVG}}}rect"):
        classes = rect.get("class", "").split()
        if "c" in classes:
            position = int(rect.get("x")) // 16, int(rect.get("y")) // 16
            days[position] = rect
        elif "s" in classes:
            snake.append(rect)

    # The two public reads may straddle a contribution or a UTC day boundary.
    # Never publish the new labels over yesterday's cells or a stale route.
    if days.keys() != positions.keys() or any(
        int(levels.get(rect.get("class").split()[-1], 0)) != LEVELS.index(positions[pos]["contributionLevel"])
        for pos, rect in days.items()
    ):
        raise ValueError("The snake and the public calendar come from different snapshots")
    if not snake:
        raise ValueError("The upstream image has no snake")

    bg, ink, muted, border, palette = THEMES[theme]
    root = ET.Element(f"{{{SVG}}}svg", width="746", height="202", viewBox="10 0 746 202",
                      role="img", attrib={"aria-labelledby": "title description"})
    draw(root, "title", id="title").text = f"Johnpaul's contribution snake — {heading}"
    draw(root, "desc", id="description").text = (
        "A violet snake follows the green days on my contribution calendar. "
        "Darker or brighter green marks higher activity in light or dark mode, respectively."
    )
    # Reuse each upstream crossing time. Fade back to its real level so the
    # calendar is still readable near the end of the route.
    duration_ms = int(re.search(r"\.c\{[^}]*?(\d+)ms", css)[1])

    def restore_day(match):
        name, before, level, crossing = match.groups()
        restore = min(100, float(crossing) + 700 / duration_ms * 100)
        return (f"@keyframes {name}{{{before}%{{fill:var(--c{level})}}"
                f"{crossing}%{{fill:var(--ce)}}{restore:.4f}%,100%{{fill:var(--c{level})}}}}")

    css, count = re.subn(
        r"@keyframes (c\w+)\{([\d.]+)%\{fill:var\(--c(\d+)\)\}([\d.]+)%,100%\{fill:var\(--ce\)\}\}",
        restore_day, css)
    if count != len(levels):
        raise ValueError("Could not match the crossing time of every active day")
    variables = ";".join(f"--c{i}:{color}" for i, color in enumerate(palette))
    draw(root, "style").text = css + f"""
:root{{--ce:{palette[0]};--cb:transparent;{variables}}}
text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:{ink};font-size:12px}}
.heading{{font-size:17px;font-weight:600}}
.muted{{fill:{muted};font-size:13px}}
.c{{width:12.3077px;height:12.3077px;stroke:none}}
@media(max-width:530px){{
  .heading{{font-size:27px}}
  .month,.weekday,.muted{{font-size:20px}}
  .minor-month{{display:none}}
}}
@media(prefers-reduced-motion:reduce){{.c{{animation:none!important}}.s{{display:none}}}}
"""
    draw(root, "rect", width="766", height="202", fill=bg)
    draw(root, "text", x="10", y="25", **{"class": "heading"}).text = heading
    draw(root, "rect", x="10.5", y="37.5", width="745", height="160", rx="6",
         fill=bg, stroke=border)
    # The reference uses 10px days on a 13px pitch. Also fit an extra week if
    # GitHub includes one around a leap-year boundary.
    columns = max(column for column, _ in days) + 1
    pitch = min(13, 676 / max(columns - 1, 1))
    month_start = 0
    for month in calendar["months"]:
        # A single remaining week is narrower than its three-letter label.
        if month["totalWeeks"] >= 2:
            month_class = "month" if month["name"] in ("Jan", "Apr", "Jul", "Oct") else "month minor-month"
            draw(root, "text", x=f"{55 + month_start * pitch:.2f}", y="66",
                 **{"class": month_class}).text = month["name"]
        month_start += month["totalWeeks"]
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        draw(root, "text", x="50", y=str(81 + 13 * row),
             **{"class": "weekday", "text-anchor": "end"}).text = label

    # The upstream grid has 16-unit spacing and offsets its cells by 2 units.
    # Apply the same transform to both cells and snake to preserve its path.
    scale = pitch / 16
    clip = draw(draw(root, "defs"), "clipPath", id="grid")
    draw(clip, "rect", x="52", y="69", width="692", height="94")
    viewport = draw(root, "g", **{"clip-path": "url(#grid)"})
    grid = draw(viewport, "g", transform=f"translate({55 - 2 * scale:.5f} 70.375) scale({scale:.8f} .8125)")
    for pos, rect in days.items():
        day = positions[pos]
        count = day["contributionCount"]
        draw(rect, "title").text = f"{day['date']} · {count} contribution{'s' if count != 1 else ''}"
        grid.append(rect)
    for segment in reversed(snake):
        grid.append(segment)
    help_link = draw(root, "a", href="https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference#what-counts-as-a-contribution")
    draw(help_link, "text", x="51", y="182", **{"class": "muted"}).text = "Learn how we count contributions"
    draw(root, "text", x="633", y="182", **{"class": "muted", "text-anchor": "end"}).text = "Less"
    for i, color in enumerate(palette):
        draw(root, "rect", x=str(638 + 13 * i), y="173", width="10", height="10", rx="2", fill=color)
    draw(root, "text", x="704", y="182", **{"class": "muted"}).text = "More"
    ET.ElementTree(root).write(destination, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("calendar_json", type=Path)
    args = parser.parse_args()
    calendar = json.loads(args.calendar_json.read_text())["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    for theme in THEMES:
        render(args.directory / f"snake-{theme}.svg", args.directory / f"calendar-{theme}.svg",
               theme, calendar)
