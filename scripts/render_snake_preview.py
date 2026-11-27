"""Render the profile close-up from Platane/snk's generated route."""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
PALETTES = {
    "dark": ("#111821", "#303b4b", "#73d997", "#29203d"),
    "light": ("#f7f8fc", "#d9dce8", "#218344", "#ffffff"),
}


def draw(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", attributes)


def preview(source, destination, theme):
    original = ET.parse(source).getroot()
    css = original.find(f"{{{SVG}}}style").text
    # These selectors belong to the pinned generator. Keep the original body
    # animations, including its variable speed and pauses, in both themes.
    body_css = css[css.index(".s{"):]
    duration = re.search(r"(\d+ms)", body_css)[1]
    snake_color = re.search(r"--cs:([^;}]+)", css)[1]
    head = re.search(r"@keyframes s0(\{.*?\}\})\.s\.s0", body_css)[1]

    def follow(match):
        # Partially follow the head, leaving room to see turns and its tail.
        x, y = map(float, match.groups())
        return f"translate({108 - 0.84 * x:.2f}px,{49 - y:.2f}px)"

    translation = r"translate\((-?[\d.]+)px,(-?[\d.]+)px\)"
    camera = re.sub(translation, follow, head)
    first_position = re.search(r"\.s\.s0\{transform:([^;}]+)", body_css)[1]
    resting_camera = re.sub(translation, follow, first_position)
    background, border, food, eyes = PALETTES[theme]
    result = ET.Element(f"{{{SVG}}}svg", width="360", height="112", viewBox="0 0 360 112",
                        role="img", attrib={"aria-labelledby": "title"})
    draw(result, "title", id="title").text = "Johnpaul’s contribution snake, close up"
    style = draw(result, "style")
    rules = [
        f":root{{--cs:{snake_color}}}", body_css,
        f"@keyframes follow{camera}",
        f".camera{{transform:{resting_camera};animation:follow {duration} linear infinite}}",
    ]
    drawing = draw(result, "defs")
    clip = draw(drawing, "clipPath", id="bounds")
    draw(clip, "rect", x="1", y="1", width="358", height="110", rx="11")
    draw(result, "rect", x=".5", y=".5", width="359", height="111", rx="12",
         fill=background, stroke=border)
    viewport = draw(result, "g", **{"clip-path": "url(#bounds)"})
    scene = draw(viewport, "g", **{"class": "camera"})

    # Each occupied day has a generated CSS keyframe for when it gets eaten.
    # Show the next three as food, leaving the full calendar in the linked SVG.
    eaten = {name: float(percent) for name, percent in re.findall(
        r"@keyframes (c\w+)\{([\d.]+)%\{fill:", css)}
    cells = [(eaten[name], rect) for rect in original.findall(f"{{{SVG}}}rect")
             for name in rect.get("class", "").split() if name in eaten]
    cells.sort(key=lambda entry: entry[0])
    for i, (end, rect) in enumerate(cells):
        start = cells[i - 3][0] if i >= 3 else 0
        initial = 0 if start else 1
        reveal = f"{start}%{{opacity:1}}" if start else ""
        rules.append(f"@keyframes food{i}{{0%{{opacity:{initial}}}{reveal}{end}%,100%{{opacity:0}}}}")
        dot = draw(scene, "g", **{"class": "food", "opacity": str(initial),
                   "style": f"animation:food{i} {duration} steps(1,end) infinite"})
        cx, cy = str(float(rect.get("x")) + 6), str(float(rect.get("y")) + 6)
        draw(dot, "circle", cx=cx, cy=cy, r="6.8", fill="none", stroke=food, opacity=".32")
        draw(dot, "circle", cx=cx, cy=cy, r="3.5", fill=food)

    segments = [rect for rect in original.findall(f"{{{SVG}}}rect")
                if "s" in rect.get("class", "").split()]
    for segment in reversed(segments):
        group = draw(scene, "g", **{"class": segment.attrib.pop("class")})
        group.append(segment)
        if "s0" in group.get("class").split():
            for x in ("5.4", "10.6"):
                draw(group, "circle", cx=x, cy="5.7", r="1.15", fill=eyes)
    rules.append("@media(prefers-reduced-motion:reduce){.camera,.s,.food{animation:none!important}}")
    style.text = "\n".join(rules)
    ET.ElementTree(result).write(destination, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing snake-dark.svg and snake-light.svg")
    directory = parser.parse_args().directory
    for mode in PALETTES:
        preview(directory / f"snake-{mode}.svg", directory / f"preview-{mode}.svg", mode)
