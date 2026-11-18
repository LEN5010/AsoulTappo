#!/usr/bin/env python3
"""Build 嘉然然龙's visible wing layer from the artist's 19 numbered PNGs.

    server/.venv/bin/python scripts/make_dragon_wings.py SOURCE_DIR

SOURCE_DIR holds 01.png, 2 (1).png (or 2.png), and 3.png through 19.png.
"""
import argparse
import json
import math
from io import BytesIO
from pathlib import Path
from statistics import linear_regression

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from make_form_loop import CHARACTERS, GAP

SKIN = CHARACTERS / "嘉然然龙"
COUNT = 19
MS = 83


def colour_mask(image, ranges):
    mask = image.getchannel("A").point(lambda a: 255 if a > 240 else 0)
    for channel, (lo, hi) in zip(image.split(), ranges):
        band = channel.point(lambda v: 255 if lo <= v <= hi else 0)
        mask = ImageChops.darker(mask, band)
    return mask


def landmarks(image):
    # Use the monitor panel and the blue irises as registration marks, away from the wings.
    screen = colour_mask(image, ((59, 63),) * 3)
    middle = round(image.height * 0.55)
    left, _, right, _ = screen.crop((0, middle, round(image.width * 0.39), middle + 1)).getbbox()
    # A vertical scan off-centre meets just the panel before it reaches the stand.
    col = left + (right - left) // 4
    column = screen.load()
    top = bottom = middle
    while column[col, top - 1]:
        top -= 1
    while column[col, bottom]:
        bottom += 1
    eyes = colour_mask(image, ((125, 175), (175, 225), (210, 250))).filter(ImageFilter.MinFilter(3)).getbbox()
    horns = colour_mask(image, ((69, 77), (91, 100), (66, 75)))
    horn_top = horns.filter(ImageFilter.MinFilter(3)).getbbox()[1]
    return ((left, right, eyes[0], eyes[2]), (horn_top, top, (eyes[1] + eyes[3]) / 2, bottom))


def wing_visibility(body):
    """Wings pass over the two long ponytails and behind the fixed foreground."""
    rgb = body.convert("RGBA")
    hair = colour_mask(rgb, ((185, 222), (140, 183), (117, 158)))
    # The right tie and keyboard divide the back hair into two disconnected fills.
    for seed in ((470, 600), (1060, 610)):
        ImageDraw.floodfill(hair, seed, 128)
    inner = hair.copy()
    ImageDraw.floodfill(inner, (930, 549), 64)
    inner = inner.point(lambda v: 255 if v == 64 else 0)
    hair = hair.point(lambda v: 255 if v == 128 else 0)
    clear = ImageChops.invert(rgb.getchannel("A"))
    # Include the outside ink of each ponytail where it meets the background.
    outer_edge = ImageChops.darker(hair.filter(ImageFilter.MaxFilter(17)), clear.filter(ImageFilter.MaxFilter(17)))
    visible = ImageChops.lighter(clear, ImageChops.lighter(hair, outer_edge))
    # Reserve the keyboard lip and its outline, including the resampling footprint.
    lip_box = (480, 553, 1040, 620)
    lip = colour_mask(rgb.crop(lip_box), ((218, 255), (131, 191), (144, 206)))
    visible.paste(0, lip_box, lip.filter(ImageFilter.MaxFilter(23)))
    # The inner membrane meets the key directly; leave just its ink and sampling margin.
    inner.paste(0, lip_box, lip.filter(ImageFilter.MaxFilter(19)))
    return ImageChops.lighter(visible, inner)


def wing_layer(path, body, anchors, outside):
    with Image.open(path) as source:
        xs, ys = landmarks(source)
        sx, dx = linear_regression(anchors[0], xs)
        sy, dy = linear_regression(anchors[1], ys)
        aligned = source.convert("RGBa").transform(body.size, Image.Transform.AFFINE,
                    (sx, 0, dx, 0, sy, dy), Image.Resampling.BICUBIC)

    # The artist has already drawn the visible outlines at the hair, ears and monitor.
    # Find new membrane paint, then take the ink immediately around it from the same frame.
    rgb = aligned.convert("RGBA")
    green = colour_mask(rgb, ((65, 144), (85, 157), (60, 132)))
    cream = colour_mask(rgb, ((191, 237), (180, 224), (151, 201)))
    delta = ImageChops.difference(aligned, body)
    changed = delta.getchannel(0)
    for band in delta.split()[1:]:
        changed = ImageChops.lighter(changed, band)
    new_paint = changed.point(lambda v: 255 if v > 28 else 0)
    core = ImageChops.darker(ImageChops.lighter(green, cream), new_paint)
    # Limit the extraction to the two wing regions. The desk starts at y=626.
    regions = Image.new("L", body.size)
    for box in ((145, 105, 690, 627), (860, 105, body.width, 627)):
        regions.paste(255, box)
    core = ImageChops.darker(core, regions).filter(ImageFilter.MinFilter(3))
    # Dilation with a large square is cheaper on a half-size mask.
    near = core.reduce(2).filter(ImageFilter.MaxFilter(23)).resize(body.size, Image.Resampling.BILINEAR)
    # Beyond the body silhouette, keep the entire painted tip, including its solid ink cap.
    near = ImageChops.darker(ImageChops.lighter(near, outside), regions)
    rgb.putalpha(ImageChops.darker(rgb.getchannel("A"), near))
    return rgb


def draw_wing_roots(frame, index):
    """Animate the exposed membrane between each hair tie and the collar.

    The small strokes on the supplied cels vary in shape and direction. Each
    root uses one cubic profile through the flap, hidden at its ends by the
    tie and collar. The existing visibility mask supplies those silhouettes.
    """
    lift = (1 - math.cos(math.tau * (index + 0.25) / COUNT)) / 2
    # From tie to collar, cubic heights in canvas pixels at rest and fully raised.
    profiles = (
        (582, 685, (560, 552, 570, 573), (520, 518, 524, 540)),
        (965, 881, (560, 550, 568, 568), (537, 535, 538, 547)),
    )
    top, bottom = 494, 583
    for tie, collar, folded, raised in profiles:
        heights = [a + (b - a) * lift for a, b in zip(folded, raised)]
        left, right = sorted((tie, collar))
        scale = 3
        size = ((right - left + 1) * scale, (bottom - top) * scale)
        patch = Image.new("RGBA", size)
        edge = []
        for x in range(size[0]):
            t = (left + x / scale - tie) / (collar - tie)
            t = min(1.0, max(0.0, t))
            v = 1 - t
            y = (v**3 * heights[0] + 3 * v**2 * t * heights[1]
                 + 3 * v * t**2 * heights[2] + t**3 * heights[3])
            edge.append((x, round((y - top) * scale)))
        draw = ImageDraw.Draw(patch)
        draw.polygon([(0, 0), (size[0] - 1, 0), *reversed(edge)], fill=(221, 208, 186, 255))
        draw.line(edge, fill=(55, 43, 34, 255), width=7 * scale)
        box = (left, top, right + 1, bottom)
        frame.paste(patch.resize((right - left + 1, bottom - top), Image.Resampling.LANCZOS), box)


def build(source_dir):
    body = Image.open(SKIN / "formImage.webp").convert("RGBA")
    anchors = landmarks(body)
    wide = Image.new("RGBa", (1536, body.height))
    wide.paste(body.convert("RGBa"))
    silhouette = wide.getchannel("a").point(lambda a: 255 if a > 8 else 0)
    outside = ImageChops.invert(silhouette.reduce(2).filter(ImageFilter.MaxFilter(13)).resize(wide.size))
    visible = wing_visibility(wide)
    frames = []
    for i in range(1, COUNT + 1):
        path = source_dir / f"{i}.png"
        if i == 1 or (i == 2 and (source_dir / "2 (1).png").exists()):
            path = source_dir / ("01.png" if i == 1 else "2 (1).png")
        frame = wing_layer(path, wide, anchors, outside)
        draw_wing_roots(frame, i - 1)
        frame.putalpha(ImageChops.darker(frame.getchannel("A"), visible))
        frames.append(frame)

    union = frames[0].getchannel("A")
    for frame in frames[1:]:
        union = ImageChops.lighter(union, frame.getchannel("A"))
    x, y, right, bottom = union.getbbox()
    w, h = right - x, bottom - y
    # Five-eighths scale fits all 19 poses in a single WebP strip.
    w, h = (w + 7) // 8 * 8, (h + 7) // 8 * 8
    size = (5 * w // 8, 5 * h // 8)
    stride = size[0] + GAP
    strip = Image.new("RGBA", (stride * COUNT, size[1]))
    for i, frame in enumerate(frames):
        cell = frame.crop((x, y, x + w, y + h)).resize(size, Image.Resampling.HAMMING)
        strip.paste(cell, (i * stride, 0))
    encoded = BytesIO()
    strip.save(encoded, format="WEBP", quality=91, alpha_quality=100, method=6)
    (SKIN / "formLoop.webp").write_bytes(encoded.getvalue())
    spec = dict(x=x, y=y, w=w, h=h, frames=COUNT, ms=MS, width=body.width, height=body.height)
    (SKIN / "formLoop.json").write_text(json.dumps(spec) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    build(parser.parse_args().source_dir)
