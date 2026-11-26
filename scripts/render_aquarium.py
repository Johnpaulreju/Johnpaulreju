"""Place an upstream Git Koi animation in Miko's pixel-art aquarium."""

import argparse
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageSequence


TANK = Path(__file__).resolve().parents[1] / "assets" / "miko" / "tank.png"
SIZE = (720, 360)
BUBBLE_COLORS = [(71, 139, 151), (139, 201, 193)]


def read_koi(source):
    """Crop transparently padded frames without losing their original positions."""
    sprites = []
    counts = Counter()
    with Image.open(source) as image:
        size = image.size
        for frame in ImageSequence.Iterator(image):
            rgba = frame.convert("RGBA")
            bounds = rgba.getchannel("A").getbbox()
            sprite = rgba.crop(bounds) if bounds else None
            if sprite:
                for count, color in sprite.getcolors(sprite.width * sprite.height):
                    if color[3]:
                        counts[color[:3]] += count
            sprites.append((sprite, bounds, frame.info.get("duration", 100)))
    if not counts:
        raise ValueError("The source animation contains no visible koi.")
    return sprites, size, counts


def fish_palette(tank, counts):
    """Share a palette across frames, retaining the upstream sprite's exact colors."""
    raw = tank.getpalette()
    colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    for color in BUBBLE_COLORS + [rgb for rgb, _ in counts.most_common()]:
        if color not in colors and len(colors) < 255:
            colors.append(color)
    indices = {rgb: i for i, rgb in enumerate(colors)}
    # Custom upstream palettes may exceed GIF's color limit.
    for rgb in counts.keys() - indices.keys():
        indices[rgb] = min(range(len(colors)), key=lambda n: sum(
            (a - b) ** 2 for a, b in zip(rgb, colors[n])
        ))
    tank.putpalette(bytes(channel for color in colors for channel in color))
    return indices


def bubbles(frame, phase, indices):
    """A pair of small bubble trails completes one cycle per swimming loop."""
    draw = ImageDraw.Draw(frame)
    outline, light = (indices[c] for c in BUBBLE_COLORS)
    for x, n, shift in [(648, 5, 0.0), (78, 3, 0.23)]:
        for i in range(n):
            age = (phase + i / n + shift) % 1
            y = round(275 - age * 227)
            center = round(x + 5 * math.sin(2 * math.pi * (age + i / n)))
            radius = 2 if i % 2 else 3
            draw.ellipse((center-radius, y-radius, center+radius, y+radius), outline=outline)
            draw.point((center-1, y-radius), fill=light)


def render(source, output):
    sprites, (source_width, source_height), counts = read_koi(source)
    with Image.open(TANK) as art:
        tank = art.resize(SIZE, Image.Resampling.NEAREST)
    indices = fish_palette(tank, counts)
    visible = [sprite for sprite, _, _ in sprites if sprite]
    scale = min(415 / max(source_width, source_height),
                270 / max(s.height for s in visible), 355 / max(s.width for s in visible))

    frames = []
    durations = [ms for _, _, ms in sprites]
    cycle = max(1, sum(durations))
    elapsed = 0
    best_score = -math.inf
    for sprite, bounds, ms in sprites:
        frame = tank.copy()
        bubbles(frame, elapsed / cycle, indices)
        elapsed += ms
        if sprite:
            width = max(1, round(sprite.width * scale))
            height = max(1, round(sprite.height * scale))
            # Keep the sprite's aspect and pose. Reframe its route for wider water.
            cx = 360 + ((bounds[0] + bounds[2]) / (2 * source_width) - 0.5) * 590
            cy = 162 + ((bounds[1] + bounds[3]) / (2 * source_height) - 0.5) * 220
            x = min(694 - width, max(26, round(cx - width / 2)))
            y = min(305 - height, max(32, round(cy - height / 2)))
            sprite = sprite.resize((width, height), Image.Resampling.NEAREST)
            pixels = bytes(indices.get(rgb[:3], 0) for rgb in sprite.get_flattened_data())
            indexed = Image.frombytes("P", sprite.size, pixels)
            indexed.putpalette(tank.getpalette())
            frame.paste(indexed, (x, y), sprite.getchannel("A"))
            # Prefer a broadside view near the middle for reduced-motion readers.
            score = width - 0.35 * height - 0.25 * abs(cx - 360)
            if score > best_score:
                best_score, still = score, frame
        frames.append(frame)

    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as staging:
        path = Path(staging)
        frames[0].save(path / "aquarium.gif", save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, disposal=1, optimize=True)
        still.save(path / "aquarium.png", optimize=True)
        for name in ("aquarium.gif", "aquarium.png"):
            (path / name).replace(output / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_koi_gif", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    render(args.input_koi_gif, args.output_dir)
