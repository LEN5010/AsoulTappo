#!/usr/bin/env python3
"""Normalise the five member dumplings (团子) for the park race.

Each 2000x2000 source is cropped to its alpha bounding box, scaled so the content width is 90%
of a 384x384 canvas, centred horizontally and bottom-aligned 3% above the lower edge
(see docs/design/amusement-park.md §6.6). Sources are not in git; rerun after replacing them:
    server/.venv/bin/python scripts/make_tuanzi.py [SOURCE_DIR] [--preview [PATH]]

Outputs client/public/assets/park/tuanzi/<member id>.webp (WebP quality 85).
With --preview, also writes a sheet with all five at the same scale and one stack of two.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("/Users/len5010/code/AsoulTappo/docs/design/assets/tuanzi")
DEFAULT_PREVIEW = Path("/Users/len5010/code/AsoulTappo/docs/design/assets/tuanzi-preview.png")
OUT = ROOT / "client/public/assets/park/tuanzi"

MEMBERS = ("jiaran", "nailin", "beila", "xinyi", "sinuo")
CANVAS = 384
CONTENT_W = round(CANVAS * 0.90)
BOTTOM_GAP = round(CANVAS * 0.03)
# Pixels fainter than this do not count toward the bounding box (stray antialiasing dust).
ALPHA_FLOOR = 8
STACK_AT = 0.60  # the upper dumpling sits at 60% of the lower one's content height

PAPER = "#FFF7F2"  # --c-50
INK = "#3A222B"  # --ink


def content_box(im: Image.Image) -> tuple[int, int, int, int]:
    mask = im.getchannel("A").point(lambda a: 255 if a >= ALPHA_FLOOR else 0)
    box = mask.getbbox()
    if box is None:
        raise SystemExit("empty image")
    return box


def normalise(src: Path) -> tuple[Image.Image, int]:
    """Return the 384px canvas and the content height on it."""
    im = Image.open(src).convert("RGBA")
    im = im.crop(content_box(im))
    h = round(im.height * CONTENT_W / im.width)
    if h > CANVAS - BOTTOM_GAP:
        raise SystemExit(f"{src.name}: content {CONTENT_W}x{h} does not fit the canvas")
    im = im.resize((CONTENT_W, h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(im, ((CANVAS - CONTENT_W) // 2, CANVAS - BOTTOM_GAP - h))
    return canvas, h


def preview(path: Path, images: dict[str, Image.Image], heights: dict[str, int]) -> None:
    font = ImageFont.load_default(size=13)
    cell = 192  # half size, the same scale for all five
    gap = 16
    scale = cell / CANVAS
    lower, upper = "jiaran", "nailin"
    lift = round(heights[lower] * STACK_AT * scale)  # upper canvas sits this much higher
    row_h = cell + lift + 30
    w = gap + (len(images) + 1) * (cell + gap)
    sheet = Image.new("RGBA", (w, 2 * row_h), PAPER)
    d = ImageDraw.Draw(sheet)
    d.rectangle((0, row_h, w, 2 * row_h), fill=INK)
    small = {m: im.resize((cell, cell), Image.Resampling.LANCZOS) for m, im in images.items()}
    for row, fg in enumerate((INK, PAPER)):
        floor = row * row_h + lift + cell  # bottom of every canvas in this row
        for i, mid in enumerate(images):
            x = gap + i * (cell + gap)
            sheet.alpha_composite(small[mid], (x, floor - cell))
            d.text((x, floor + 6), f"{mid}  h={heights[mid]}", fill=fg, font=font)
        # Shared baseline: every dumpling's bottom edge should touch it.
        y = floor - round(BOTTOM_GAP * scale)
        d.line((gap, y, gap + len(images) * (cell + gap) - gap, y), fill=(220, 130, 110, 255), width=1)
        # Stack of two: the upper dumpling's bottom edge at 60% of the lower one's content height.
        sx = gap + len(images) * (cell + gap)
        sheet.alpha_composite(small[lower], (sx, floor - cell))
        sheet.alpha_composite(small[upper], (sx, floor - cell - lift))
        d.text((sx, floor + 6), f"{upper} on {lower}", fill=fg, font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path, nargs="?", default=DEFAULT_SOURCE)
    ap.add_argument("--preview", type=Path, nargs="?", const=DEFAULT_PREVIEW)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    images: dict[str, Image.Image] = {}
    heights: dict[str, int] = {}
    total = 0
    for mid in MEMBERS:
        src = args.source / f"{mid}.webp"
        raw = Image.open(src).convert("RGBA")
        box = content_box(raw)
        im, h = normalise(src)
        out = OUT / f"{mid}.webp"
        im.save(out, "WEBP", quality=85, method=6)
        n = out.stat().st_size
        total += n
        images[mid], heights[mid] = im, h
        print(f"{mid:7} source box {box[2] - box[0]}x{box[3] - box[1]}  ->  {CONTENT_W}x{h}  {n:6d} B")
    print(f"{'total':7} {total:6d} B")

    if args.preview:
        preview(args.preview, {m: Image.open(OUT / f"{m}.webp").convert("RGBA") for m in MEMBERS}, heights)
        print(f"preview -> {args.preview}")


if __name__ == "__main__":
    main()
