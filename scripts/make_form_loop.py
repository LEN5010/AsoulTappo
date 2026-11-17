#!/usr/bin/env python3
"""Animate the parts a two-form skin's second picture adds, as a short loop.

The second pictures are the first ones plus parts. Two kinds of motion:
- a flame burns (贝拉炎头队长): the flame is lifted off the second picture, formImage.webp is written again with
  the first picture under it, and the flame is drawn moving: its root and outline stay, tongues lick up its sides,
  ripples climb through it, and now and then a small flame breaks off the tip and rises;
- a glint (乃琳法师's crown): the part stays in formImage.webp, and the frames hold only light laid over it, a
  broad and a narrow stripe sweeping across its flat colour and a star opening on its highest point as they pass.
PetView lays the frames over the second picture and steps through them while it shows; formLoop.json says
where they go on the picture and how fast they run.

The sources of the flames are the second pictures with the part drawn in, on the aligned 1280 canvas; they are
not in git. A glint reads formImage.webp.
Rerun after replacing a source or changing LOOPS:
    server/.venv/bin/python scripts/make_form_loop.py [SOURCE_DIR] [--only SKIN] [--preview PATH]

Outputs client/src/assets/characters/<skin>/formImage.webp, formLoop.webp and formLoop.json.
With --preview, also writes a sheet of the frames over the second picture, at full size and at the
pet's usual size. Pillow only; the output is deterministic.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = ROOT / "client/src/assets/characters"
DEFAULT_SOURCE = ROOT / "docs/assets/form-loops"
# Transparent columns after each frame of the strip (the strip's width is frames x (w + GAP)), so a frame
# drawn at a fractional offset never shows an edge of the next one.
GAP = 4
CELL = 4
TAU = 2 * math.pi


@dataclass(frozen=True)
class Flame:
    # Where the part is on the 1280 canvas; other changes of the second picture (the chest emblem) stay put.
    search: tuple[int, int, int, int]
    frames: int
    ms: int
    # How far tongues reach above or fall below the outline, as a share of the part's height.
    lick: float
    # How far ripples push it sideways, as a share of its width.
    ripple: float
    # Pieces of the tip that break off in one loop: when (0..1) and which way they drift (share of the width).
    pieces: tuple[tuple[float, float], ...]
    # How long a piece lives (share of the loop) and how high it rises (share of the height).
    piece_life: float
    piece_rise: float
    # Change of brightness, as a share.
    flicker: float


@dataclass(frozen=True)
class Glint:
    # Where the part is on the 1280 canvas.
    search: tuple[int, int, int, int]
    frames: int
    ms: int
    # The frame the sweep starts on, and how many frames it takes to cross the part.
    start: int
    sweep: int
    # How far the stripes lean: pixels to the right per pixel up.
    slant: float
    # Widths of the broad stripe, the gap behind it and the narrow stripe after that, in pixels.
    stripes: tuple[int, int, int]
    # How far the stripes' colour goes from the part's flat colour towards warm white (0..1).
    lift: float
    # The star on the part's highest point: outer radius in pixels and how many frames it shows, opening as the
    # broad stripe reaches it; filled with `star_fill` and outlined with `ink`, the drawing's outline colour.
    star: int
    star_frames: int
    star_fill: tuple[int, int, int]
    ink: tuple[int, int, int]


LOOPS: dict[str, Flame | Glint] = {
    "贝拉炎头队长": Flame(
        search=(600, 0, 900, 262), frames=12, ms=75, lick=0.11, ripple=0.06,
        pieces=((0.0, -0.08), (0.5, 0.1)), piece_life=0.45, piece_rise=0.3, flicker=0.07,
    ),
    "乃琳法师": Glint(
        search=(570, 320, 980, 475), frames=40, ms=60, start=6, sweep=12, slant=0.5, stripes=(34, 8, 10), lift=0.6,
        star=20, star_frames=7, star_fill=(255, 255, 255), ink=(39, 28, 26),
    ),
}

# Waves that make up the motion, each: weight, cycles across the width, cycles up the height, cycles per loop
# (whole numbers, so the last frame leads back into the first), phase. A wave whose phase falls with time while
# it rises with height travels upwards.
LICK = ((0.5, 1.3, 0.9, 2, 0.4), (0.3, 2.6, 1.4, 3, 2.1), (0.2, 4.1, 2.6, 5, 4.0))
# Few cycles up the height: the thin tail at the tip leans with the ripple instead of kinking.
RIPPLE = ((0.6, 0.7, 0.8, 2, 0.0), (0.4, 1.9, 1.3, 3, 1.7))


def waves(terms: tuple[tuple[float, float, float, int, float], ...], u: float, v: float, t: float) -> float:
    return sum(a * math.sin(TAU * (fx * u + fy * v - c * t) + p) for a, fx, fy, c, p in terms)


def changed(base: Image.Image, form: Image.Image, search: tuple[int, int, int, int]) -> Image.Image:
    """Pixels inside `search` where the second picture differs from the first. Thin lines where the two
    pictures were cut out of their backgrounds a little differently are dropped."""
    diff = ImageChops.difference(base.convert("RGBa"), form.convert("RGBa"))
    channels = diff.split()
    most = channels[0]
    for ch in channels[1:]:
        most = ImageChops.lighter(most, ch)
    core = most.point(lambda v: 255 if v > 30 else 0)
    keep = Image.new("L", core.size, 0)
    keep.paste(255, search)
    core = ImageChops.multiply(core, keep)
    return core.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))


def part_mask(base: Image.Image, form: Image.Image, search: tuple[int, int, int, int]) -> Image.Image:
    """Pixels of the flame, widened to take in its soft glow."""
    keep = Image.new("L", base.size, 0)
    keep.paste(255, search)
    return ImageChops.multiply(changed(base, form, search).filter(ImageFilter.MaxFilter(21)), keep)


def unmix(base: Image.Image, form: Image.Image, mask: Image.Image) -> Image.Image:
    """The part alone: for each pixel under the mask, the least opaque colour that, laid over the first
    picture, gives the second one."""
    w, h = form.size
    bp, fp, mp = base.load(), form.load(), mask.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    x0, y0, x1, y1 = mask.getbbox()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if not mp[x, y]:
                continue
            br, bg, bb, ba = bp[x, y]
            fr, fg, fb, fa = fp[x, y]
            ab, af = ba / 255, fa / 255
            under = (br * ab, bg * ab, bb * ab)
            over = (fr * af, fg * af, fb * af)
            # Coverage from the alpha channels, where the first picture lets the background through.
            alpha = (af - ab) / (1 - ab) if ab < 0.96 else 0.0
            # Coverage from colour: the least that keeps every channel of the part within 0..255.
            for u, o in zip(under, over):
                if o > u:
                    alpha = max(alpha, (o - u) / (255 - u) if u < 255 else 1.0)
                elif o < u:
                    alpha = max(alpha, (u - o) / u)
            alpha = min(1.0, alpha)
            if alpha < 1 / 255:
                continue
            colour = [round(min(255.0, max(0.0, (o - (1 - alpha) * u) / alpha))) for u, o in zip(under, over)]
            # Fire is bright: a dark result is an outline the two cut-outs edged differently, not the part.
            if max(colour) < 128:
                continue
            op[x, y] = (*colour, round(alpha * 255))
    return out


def burning(part: Image.Image, root: tuple[float, float], size: tuple[float, float], loop: Flame, t: float) -> Image.Image:
    """The part at time t of the loop (0..1). Nothing moves at the root and more towards the tip: the outline
    rises and falls column by column as tongues travel up it, and ripples climb through the strokes inside."""
    rx, ry = root
    width, height = size

    def source(x: float, y: float) -> tuple[float, float]:
        # Above the tip there is only its thin tail to draw from, so the motion stops growing there.
        v = min(1.12, max(0.0, (ry - y) / height))
        u = (x - rx) / width
        # Full from the shoulders up, so tongues rise along the sides and not only from the tip.
        grow = min(1.0, v / 0.7) ** 1.3
        dx = width * loop.ripple * grow * waves(RIPPLE, u, v, t)
        # Taken from lower down, the picture reaches higher: a tongue.
        dy = height * loop.lick * grow * waves(LICK, u, v, t)
        return x - dx, y + dy

    w, h = part.size
    mesh = []
    for y in range(0, h, CELL):
        for x in range(0, w, CELL):
            x1, y1 = min(w, x + CELL), min(h, y + CELL)
            quad = (*source(x, y), *source(x, y1), *source(x1, y1), *source(x1, y))
            mesh.append(((x, y, x1, y1), quad))
    return part.convert("RGBa").transform(part.size, Image.Transform.MESH, mesh, resample=Image.Resampling.BICUBIC)


def small_flame(part: Image.Image) -> Image.Image:
    """What breaks off the tip: the whole part, made small, so it keeps the painted colours."""
    box = part.getchannel("A").point(lambda v: 255 if v > 4 else 0).getbbox()
    return part.crop(box).convert("RGBa")


def flame_frame(part: Image.Image, root: tuple[float, float], tip: tuple[float, float], size: tuple[float, float],
                loop: Flame, t: float) -> Image.Image:
    """The burning part, the pieces of the tip in the air at time t, and the flicker."""
    out = burning(part, root, size, loop, t).convert("RGBA")
    piece = small_flame(part)
    for born, drift in loop.pieces:
        age = ((t - born) % 1.0) / loop.piece_life
        if age >= 1:
            continue
        # Leaves the tip quickly and slows as it rises, shrinking and fading on the way.
        rise = 1 - (1 - age) ** 2
        scale = 0.24 - 0.12 * age
        fade = min(1.0, age * 4) * (1 - age) ** 0.8
        small = piece.resize((max(1, round(piece.width * scale)), max(1, round(piece.height * scale))), Image.Resampling.LANCZOS)
        small = small.convert("RGBA")
        small.putalpha(small.getchannel("A").point(lambda a: round(a * fade)))
        cx = tip[0] + drift * size[0] * rise
        bottom = tip[1] + small.height * 0.5 - size[1] * loop.piece_rise * rise
        out.alpha_composite(small, (round(cx - small.width / 2), round(bottom - small.height)))
    gain = 1 + loop.flicker * (0.7 * math.sin(TAU * 2 * t) + 0.3 * math.sin(TAU * 3 * t + 1.2))
    r, g, b, a = out.split()
    lift = lambda c: min(255, round(c * gain))
    return Image.merge("RGBA", (r.point(lift), g.point(lift), b.point(lift), a))


def flame_frames(base: Image.Image, form: Image.Image, loop: Flame):
    """The second picture without the flame, the frames, and where they go."""
    mask = part_mask(base, form, loop.search)
    part = unmix(base, form, mask)
    body = form.copy()
    body.paste(base, (0, 0), mask)

    left, top, right, bottom = part.getchannel("A").point(lambda v: 255 if v > 4 else 0).getbbox()
    height, width = bottom - top, right - left
    # The root: the middle of the part's lowest quarter, weighted by how opaque it is.
    alpha = part.getchannel("A").load()
    total = weighted = 0.0
    for y in range(bottom - height // 4, bottom):
        for x in range(left, right):
            total += alpha[x, y]
            weighted += alpha[x, y] * x
    root = (weighted / total, float(bottom))
    # The tip: the middle of the highest row that is mostly opaque.
    solid = part.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    head = solid.getbbox()[1]
    row = [x for x in range(left, right) if alpha[x, head] > 128]
    tip = (sum(row) / len(row), float(head))

    side = math.ceil(width * loop.ripple) + 8
    lift = math.ceil(height * (loop.lick * 1.15 + loop.piece_rise + 0.1)) + 8
    box = (left - side, top - lift, right + side, bottom + 4)
    local = part.crop(box)
    at = lambda p: (p[0] - box[0], p[1] - box[1])

    frames = [flame_frame(local, at(root), at(tip), (width, height), loop, k / loop.frames) for k in range(loop.frames)]
    return body, frames, box


def stripe_cover(u: float, left: float, right: float) -> float:
    """How much of a pixel centred at u lies between left and right."""
    return max(0.0, min(u + 0.5, right) - max(u - 0.5, left))


def star_image(radius: float, turn: float, fill: tuple[int, int, int], ink: tuple[int, int, int]) -> Image.Image:
    """A four-pointed star, one flat colour with an outline, drawn large and scaled down so its edges are smooth."""
    scale = 4
    side = math.ceil(2 * radius + 8) * scale
    im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    centre = side / 2
    points = []
    for i in range(8):
        r = radius * scale * (1.0 if i % 2 == 0 else 0.4)
        a = turn + i * math.pi / 4 - math.pi / 2
        points.append((centre + r * math.cos(a), centre + r * math.sin(a)))
    ImageDraw.Draw(im).polygon(points, fill=(*fill, 255), outline=(*ink, 255), width=max(1, round(radius * 0.12 * scale)))
    return im.resize((side // scale, side // scale), Image.Resampling.LANCZOS)


def glint_frames(base: Image.Image, form: Image.Image, loop: Glint):
    """Frames of light over the part: the stripes take the part's flat colour towards warm white, fully on the
    flat colour and less on the soft edge towards its outline, so the outline stays dark. Most frames are empty."""
    # Where a line of the first picture under the part comes close to its colour the difference misses single
    # pixels; closing the mask takes them back.
    mask = changed(base, form, loop.search).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    x0, y0, x1, y1 = mask.getbbox()
    fp, mp = form.load(), mask.load()
    inside = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if mp[x, y]]
    lum = lambda c: (c[0] + c[1] + c[2]) / 3
    flat = sorted(fp[x, y][:3] for x, y in inside if lum(fp[x, y]) > lum(loop.ink) + 90)
    fill = flat[len(flat) // 2]
    dark, light = lum(loop.ink), lum(fill)
    weight = {}
    for x, y in inside:
        c = fp[x, y]
        if c[3] < 255 or lum(c) > light + 25:
            continue
        w = min(1.0, max(0.0, (lum(c) - dark) / (light - dark)))
        # The part is warm; grey hair the closing took in is not lit.
        if w > 0 and c[0] - c[2] >= 0.5 * (fill[0] - fill[2]) * w:
            weight[x, y] = w
    lit = tuple(round(f + loop.lift * (t - f)) for f, t in zip(fill, (255, 250, 225)))

    # A stripe is the set of pixels with the same u; u grows to the right and leans the stripes like /.
    mid = (y0 + y1) / 2
    at = lambda x, y: x + loop.slant * (y - mid)
    broad, gap, narrow = loop.stripes
    first, last = at(x0, y0) - broad, at(x1, y1) + gap + narrow
    fronts = [first + (last - first) * (j + 0.5) / loop.sweep for j in range(loop.sweep)]

    top = min(y for _, y in inside)
    row = [x for x, y in inside if y == top]
    tip = (sum(row) / len(row), float(top))
    opens = loop.start + next(j for j, p in enumerate(fronts) if p + broad / 2 >= at(*tip))

    size = form.size
    frames = []
    for k in range(loop.frames):
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        j = k - loop.start
        if 0 <= j < loop.sweep:
            p = fronts[j]
            op = out.load()
            for (x, y), w in weight.items():
                u = at(x, y)
                cover = min(1.0, stripe_cover(u, p, p + broad) + stripe_cover(u, p - gap - narrow, p - gap))
                if cover > 0:
                    op[x, y] = (*lit, round(255 * cover * w))
        i = k - opens
        if 0 <= i < loop.star_frames:
            t = (i + 0.5) / loop.star_frames
            radius = loop.star * math.sin(math.pi * t) ** 0.6
            if radius >= 2:
                star = star_image(radius, math.radians(25) * t, loop.star_fill, loop.ink)
                out.alpha_composite(star, (round(tip[0] - star.width / 2), round(tip[1] - star.height / 2)))
        frames.append(out)
    union = frames[0].getchannel("A")
    for im in frames[1:]:
        union = ImageChops.lighter(union, im.getchannel("A"))
    box = union.getbbox()
    return [im.crop(box) for im in frames], box


def build(skin: str, loop: Flame | Glint, source_dir: Path, preview: Path | None) -> None:
    folder = CHARACTERS / skin
    base = Image.open(folder / "bgImage.webp").convert("RGBA")
    if isinstance(loop, Flame):
        form = Image.open(source_dir / f"{skin}.webp").convert("RGBA")
        if base.size != form.size:
            raise SystemExit(f"{skin}: the source is {form.size}, the first picture {base.size}")
        body, frames, box = flame_frames(base, form, loop)
        body.save(folder / "formImage.webp", "WEBP", lossless=True, quality=100, method=6)
    else:
        form = body = Image.open(folder / "formImage.webp").convert("RGBA")
        frames, box = glint_frames(base, form, loop)
    cw, ch = box[2] - box[0], box[3] - box[1]
    strip = Image.new("RGBA", ((cw + GAP) * loop.frames, ch), (0, 0, 0, 0))
    for k, im in enumerate(frames):
        strip.paste(im, (k * (cw + GAP), 0))

    # The part is painted soft, so the strip takes lossy colour with exact alpha.
    strip.save(folder / "formLoop.webp", "WEBP", quality=90, alpha_quality=100, method=6)
    # Where a frame goes on the second picture, in its pixels; the strip is the frames side by side.
    spec = {"x": box[0], "y": box[1], "w": cw, "h": ch, "frames": loop.frames, "ms": loop.ms,
            "width": form.width, "height": form.height}
    (folder / "formLoop.json").write_text(json.dumps(spec) + "\n")
    print(f"{skin}: {loop.frames} frames of {cw}x{ch} at {box[0]},{box[1]}, {(folder / 'formLoop.webp').stat().st_size // 1024} KB")

    if preview:
        write_preview(body, frames, box, preview)


def write_preview(body: Image.Image, frames: list[Image.Image], box: tuple[int, int, int, int], path: Path) -> None:
    """Each frame over the second picture, close up at full size in rows of six, and two frames of the pet at
    480 wide below. Room is added above the picture for frames that reach past its top."""
    pad = 30
    above = max(0, -box[1]) + pad
    cells = []
    for im in frames:
        whole = Image.new("RGBA", (body.width, body.height + above), (126, 196, 132, 255))
        whole.alpha_composite(body, (0, above))
        whole.alpha_composite(im, (box[0], box[1] + above))
        crop = (box[0] - pad, box[1] + above - pad, box[2] + pad, box[3] + above + pad)
        small = whole.resize((480, round(whole.height * 480 / whole.width)), Image.Resampling.LANCZOS)
        cells.append((whole.crop(crop), small))
    zw, zh = cells[0][0].size
    cols = 6
    rows = math.ceil(len(cells) / cols)
    sw, sh = cells[0][1].size
    sheet = Image.new("RGB", (max(zw * cols, sw * 2), zh * rows + sh), (255, 255, 255))
    for k, (zoom, _) in enumerate(cells):
        sheet.paste(zoom.convert("RGB"), ((k % cols) * zw, (k // cols) * zh))
    sheet.paste(cells[0][1].convert("RGB"), (0, zh * rows))
    sheet.paste(cells[len(cells) // 2][1].convert("RGB"), (sw, zh * rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--only", choices=list(LOOPS))
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    for skin, loop in LOOPS.items():
        if args.only and skin != args.only:
            continue
        preview = args.preview.with_name(f"{args.preview.stem}-{skin}{args.preview.suffix}") if args.preview else None
        build(skin, loop, args.source, preview)


if __name__ == "__main__":
    main()
