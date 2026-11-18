#!/usr/bin/env python3
"""Animate the parts a two-form skin's second picture adds, as a short loop.

The second pictures are the first ones plus parts. Two kinds of motion:
- a flame burns (贝拉炎头队长): the flame is lifted off the second picture, formImage.webp is written again with
  the first picture under it, and the flame is drawn moving: its root and outline stay, tongues lick up its sides,
  ripples climb through it, and embers lift from the moving tongues;
- an armillary turns behind the head (乃琳法师, after the instrument that floats behind the costume it is drawn
  from): nothing is taken from the pictures, the frames are drawn here. A gold ring leans a way that goes round, a
  crescent turns inside it round a star of two needles, and lights with tails circle it; the metal is shaded and
  outlined in ink, and it, the lights and a few glints glow.
PetView lays the frames over the second picture, or under it for a loop marked `behind`, and steps through them
while it shows; formLoop.json says where they go on the picture and how fast they run.

The sources of the flames are the second pictures with the part drawn in, on the aligned 1280 canvas; they are
not in git. The armillary needs no source.
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

Colour = tuple[int, int, int]

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = ROOT / "client/src/assets/characters"
DEFAULT_SOURCE = ROOT / "docs/assets/form-loops"
# Transparent columns after each frame of the strip (the strip's width is frames x (w + GAP)), so a frame
# drawn at a fractional offset never shows an edge of the next one.
GAP = 4
CELL = 4
TAU = 2 * math.pi
# The armillary is drawn this many times the kept size and scaled down, for smooth edges.
OVER = 4
Matrix = tuple[tuple[float, float, float], ...]
# Where the light on the armillary's walls comes from: up, to the left and towards the viewer.
SUN = (-0.42, 0.6, 0.68)


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
    # Embers: birth phase, horizontal launch offset and drift (shares of width), duration in cycles.
    pieces: tuple[tuple[float, float, float, float], ...]
    # Rise as a share of the original height.
    piece_rise: float
    # Change of brightness, as a share.
    flicker: float


@dataclass(frozen=True)
class Armillary:
    # Where its centre is on the 1280 canvas and the radius of the outer ring, in pixels. Other sizes are shares
    # of that radius, angles are degrees.
    centre: tuple[float, float]
    radius: float
    frames: int
    ms: int
    # How far the whole instrument is turned from facing the viewer: about the vertical, then about the horizontal.
    yaw: float
    pitch: float
    # Yaw sweep, pitch sweep and roll of the assembled instrument over one loop, in degrees.
    sweep: tuple[float, float, float]
    # The outer ring's section: half its width across and half its height along its axis.
    ring: tuple[float, float]
    # The pearl set in the outer ring: where on the ring, and its radius.
    pearl: tuple[float, float]
    # The crescent: radius of the disc, radius of the hole and how far the hole is off the centre.
    crescent: tuple[float, float, float]
    # Radii of the hub's two discs and of the dot on them.
    hub: tuple[float, float, float]
    # The star: half the length of the needle across, of the needle up, and how far the waist is from the centre.
    star: tuple[float, float, float]
    # Each light's orbit: how far it leans, which way, where the light starts, and whole turns per loop.
    lights: tuple[tuple[float, float, float, int], ...]
    # Radius of the orbits, radius of a light, and how long its tail is.
    light: tuple[float, float, float]
    # The glow round a light: how far it reaches, in radii of the light, and how strong it is in the middle (0..1).
    light_glow: tuple[float, float]
    # The glow round the metal: how far it spreads, and how much stronger than a plain blur of the outline it is.
    aura: tuple[float, float]
    # Glints, which ride with the star: where on the instrument's plane (x, y), when in the loop each is widest (0..1) and how big it gets;
    # and how long one lasts, as a share of the loop.
    glints: tuple[tuple[float, float, float, float], ...]
    glint_life: float
    # Width of the outline in pixels of the canvas, and its colour.
    ink_width: float
    ink: Colour
    # Gold from shade to light, and the shine on it; the paler metal, shaded and lit; the glow; the lights' tails;
    # the lights.
    gold: tuple[Colour, Colour, Colour, Colour]
    shine: Colour
    pale: tuple[Colour, Colour]
    glow: Colour
    cream: Colour
    white: Colour
    # The frames are kept at this share of the canvas size.
    keep: float


LOOPS: dict[str, Flame | Armillary] = {
    "贝拉炎头队长": Flame(
        search=(600, 0, 900, 262), frames=40, ms=60, lick=0.12, ripple=0.12,
        pieces=((0.04, -0.19, -0.13, 0.27), (0.22, 0.04, 0.08, 0.30),
                (0.58, 0.23, 0.16, 0.25), (0.84, -0.03, -0.12, 0.33)), piece_rise=0.34, flicker=0.075,
    ),
    # Up and to the right of the head, inside the picture's right edge; the hair covers its lower left.
    "乃琳法师": Armillary(
        centre=(1036, 120), radius=178, frames=64, ms=60, yaw=-23, pitch=12, sweep=(32, 13, 17),
        ring=(0.023, 0.081), pearl=(146, 0.082), crescent=(0.56, 0.46, 0.15), hub=(0.205, 0.15, 0.08),
        star=(1.12, 0.59, 0.061), lights=((76, 12, 36, 1), (59, 119, 166, 1), (82, 242, 282, 1)),
        light=(1.10, 0.082, 102), light_glow=(2.1, 0.63), aura=(0.043, 0.47),
        glints=((0.0, 0.58, 0.62, 0.095), (-0.82, 0.60, 0.13, 0.075)), glint_life=0.13,
        ink_width=1.7, ink=(91, 64, 51),
        gold=((131, 88, 60), (186, 137, 91), (224, 183, 138), (244, 213, 172)), shine=(255, 241, 214),
        pale=((191, 157, 124), (242, 222, 194)), glow=(255, 223, 184), cream=(246, 243, 239), white=(255, 254, 252),
        keep=0.45,
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
        # Let the two shoulders billow around the painted emblem and the narrow tip lean in the updraft.
        edge = min(1.0, abs(u) * 4)
        grow = min(1.0, v) ** 1.5 * (0.4 + 0.6 * max(v, edge))
        lean = math.sin(TAU * (t - 0.28 * v))
        dx = width * loop.ripple * grow * (lean + 0.65 * waves(RIPPLE, u, v, t))
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


def flame_frame(part: Image.Image, root: tuple[float, float], size: tuple[float, float],
                launches: list[tuple[float, float]], loop: Flame, t: float) -> Image.Image:
    out = burning(part, root, size, loop, t).convert("RGBA")
    width, height = size
    # A band of heat climbs through the paint. Keep the root steady and the gold lines legible.
    heat = Image.new("L", (1, out.height))
    for y in range(out.height):
        v = min(1.0, max(0.0, (root[1] - y) / height))
        pulse = (0.5 + 0.5 * math.cos(TAU * (2 * t - 1.6 * v))) ** 2
        heat.putpixel((0, y), round(255 * loop.flicker * v * pulse))
    warm = Image.new("RGBA", out.size, (255, 213, 100, 255))
    lit = Image.composite(warm, out, heat.resize(out.size))
    lit.putalpha(out.getchannel("A"))

    # Each ember peels from a tongue as a short sliver, then cools and tapers in the air.
    embers = Image.new("RGBA", out.size)
    draw = ImageDraw.Draw(embers)
    for (born, _, drift, life), (x0, y0) in zip(loop.pieces, launches):
        age = ((t - born) % 1.0) / life
        if age >= 1:
            continue
        rise = 1 - (1 - age) ** 1.5
        x = x0 + width * drift * (rise + 0.18 * math.sin(TAU * age))
        y = y0 - height * loop.piece_rise * rise
        length = height * life * 0.17 * (1 - 0.6 * age)
        half = length * 0.32
        alpha = round(255 * min(1.0, age / 0.13) * (1 - age) ** 0.65)
        bend = length * drift * 2
        draw.polygon([(x + bend, y - length), (x + half, y), (x - bend, y + length),
                      (x - half, y + 0.15 * length)], fill=(255, 125, 63, alpha))
        draw.ellipse((x - half * 0.48, y - length * 0.40, x + half * 0.48, y + length * 0.44),
                     fill=(255, 218, 119, alpha))
    lit.alpha_composite(embers.filter(ImageFilter.GaussianBlur(2)))
    lit.alpha_composite(embers)
    return lit


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
    side = math.ceil(width * loop.ripple * 1.7) + 8
    lift = math.ceil(height * (loop.lick * 1.15 + loop.piece_rise + 0.1)) + 8
    box = (left - side, top - lift, right + side, bottom + 4)
    local = part.crop(box)
    at = lambda p: (p[0] - box[0], p[1] - box[1])

    # Sample the silhouette at each birth phase so the ember leaves the moving painted edge.
    launches = []
    for born, offset, _, _ in loop.pieces:
        x = round(at(root)[0] + width * offset)
        edge = burning(local, at(root), (width, height), loop, born).getchannel("a")
        column = edge.crop((x, 0, x + 1, edge.height)).point(lambda a: 255 if a >= 96 else 0)
        launches.append((x, column.getbbox()[1] + 4))

    frames = [flame_frame(local, at(root), (width, height), launches, loop, k / loop.frames) for k in range(loop.frames)]
    # Store at the resolution of a 480px desktop pet on a double-density display.
    frames = [im.resize((round(im.width * 0.75), round(im.height * 0.75)), Image.Resampling.LANCZOS) for im in frames]
    return body, frames, box


def rot_x(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def rot_y(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rot_z(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def mm(a: Matrix, b: Matrix) -> Matrix:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mv(m: Matrix, v: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def lean(alpha: float, phi: float) -> Matrix:
    """Turns the z axis by alpha towards the direction phi in the xy plane, without spinning about it."""
    return mm(rot_z(phi), mm(rot_y(alpha), rot_z(-phi)))


def mix(a: Colour, b: Colour, t: float) -> Colour:
    t = min(1.0, max(0.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def turn_between(a: float, b: float) -> float:
    """The angle between two directions, 0..pi."""
    return abs((a - b + math.pi) % TAU - math.pi)


def grow(mask: Image.Image, by: float) -> Image.Image:
    """The mask and a rim of about `by` pixels round it; a thin point gets a thinner rim, so it stays a point."""
    return mask.filter(ImageFilter.GaussianBlur(by)).point(lambda v: 255 if v >= 40 else 0)


def shrink(mask: Image.Image, by: float) -> Image.Image:
    """The mask without a rim of about `by` pixels inside its edge."""
    return mask.filter(ImageFilter.GaussianBlur(by)).point(lambda v: 255 if v >= 215 else 0)


def tint(mask: Image.Image, colour: Colour) -> Image.Image:
    """One colour, as opaque as the mask says."""
    im = Image.new("RGBA", mask.size, (*colour, 0))
    im.putalpha(mask)
    return im


def soft_disc(radius: float, peak: float) -> Image.Image:
    """A round glow as a mask: `peak` (0..1) in the middle, nothing at `radius`."""
    side = max(2, round(2 * radius))
    # Pillow's gradient is 0 in the middle and 180 where the circle touches the sides of its square.
    lut = [round(255 * peak * (1 - min(1.0, v / 180) ** 2) ** 2) for v in range(256)]
    return Image.radial_gradient("L").resize((side, side), Image.Resampling.BILINEAR).point(lut)


def add_at(mask: Image.Image, spot: Image.Image, x: float, y: float) -> None:
    left, top = round(x - spot.width / 2), round(y - spot.height / 2)
    box = (left, top, left + spot.width, top + spot.height)
    mask.paste(ImageChops.add(mask.crop(box), spot), box)


def ring_points(r: float, at: tuple[float, float] = (0.0, 0.0), n: int = 96) -> list[tuple[float, float, float]]:
    return [(at[0] + r * math.cos(TAU * i / n), at[1] + r * math.sin(TAU * i / n), 0.0) for i in range(n)]


def armillary_frame(loop: Armillary, t: float, size: tuple[int, int], origin: tuple[float, float]) -> Image.Image:
    """One frame, OVER times the kept size; `origin` is where it starts on the picture and t runs 0..1.
    Space is x to the right, y up and z towards the viewer, in units of the ring's radius, seen without
    perspective. The metal parts are shaded shapes with a rim of ink, laid from the back to the front over a
    glow of their own outline; the lights and the glints are light alone, without ink."""
    k = loop.keep * OVER
    unit = loop.radius * k
    ox, oy = (loop.centre[0] - origin[0]) * k, (loop.centre[1] - origin[1]) * k
    phase = TAU * t
    yaw = math.radians(loop.yaw + loop.sweep[0] * math.cos(phase))
    pitch = math.radians(loop.pitch + loop.sweep[1] * math.sin(phase))
    roll = math.radians(loop.sweep[2] * math.sin(phase + 0.5))
    face = mm(rot_z(roll), mm(rot_x(pitch), rot_y(yaw)))
    oy -= unit * 0.022 * math.sin(phase)
    put = lambda p: (ox + unit * p[0], oy - unit * p[1])
    blank = lambda: Image.new("RGBA", size, (0, 0, 0, 0))
    empty = lambda: Image.new("L", size, 0)
    # The parts from the back to the front, and whether each takes a rim of ink.
    parts: list[tuple[Image.Image, bool]] = []

    # The lights: a glow, a tail that fades, a white core. What is behind the plane of the instrument goes
    # under it, the rest over it.
    rho, radius, tail = loop.light
    sides = [[empty(), empty(), empty()], [empty(), empty(), empty()]]
    steps = 48
    for alpha, phi, start, turns in loop.lights:
        # Sample the pearl's earlier positions as its orbit gently swivels. Local z
        # places each piece of its trail on the correct side of the metal plane.
        path = []
        for j in range(steps + 1):
            past = phase - math.radians(tail) * j / (steps * abs(turns))
            swivel = math.radians(22) * math.sin(past)
            orbit = lean(math.radians(alpha), math.radians(phi) + swivel)
            angle = math.radians(start) + turns * past
            path.append(mv(orbit, (rho * math.cos(angle), rho * math.sin(angle), 0.0)))
        projected = [mv(face, p) for p in path]
        flat = [put(p) for p in projected]
        for j in range(steps):
            (x0, y0), (x1, y1) = flat[j], flat[j + 1]
            d = math.hypot(x1 - x0, y1 - y0) or 1.0
            nx, ny = -(y1 - y0) / d, (x1 - x0) / d
            h0, h1 = (unit * radius * 0.47 * (1 - i / steps) ** 0.9 for i in (j, j + 1))
            shade = round(255 * (1 - j / steps) ** 0.87)
            draw = ImageDraw.Draw(sides[(path[j][2] + path[j + 1][2]) / 2 >= 0][1])
            draw.polygon([(x0 + nx * h0, y0 + ny * h0), (x1 + nx * h1, y1 + ny * h1), (x1 - nx * h1, y1 - ny * h1), (x0 - nx * h0, y0 - ny * h0)],
                         fill=shade)
            draw.ellipse((x0 - h0, y0 - h0, x0 + h0, y0 + h0), fill=shade)
        x, y = flat[0]
        r = unit * radius * (1 + 0.18 * projected[0][2] / rho)
        glow, _, core = sides[path[0][2] >= 0]
        add_at(glow, soft_disc(r * loop.light_glow[0], loop.light_glow[1]), x, y)
        ImageDraw.Draw(core).ellipse((x - r, y - r, x + r, y + r), fill=255)

    def lights(side: list[Image.Image]) -> Image.Image:
        glow, trail, core = side
        wide = trail.filter(ImageFilter.GaussianBlur(unit * 0.05)).point(lambda v: round(v * 0.65))
        im = tint(ImageChops.add(glow, wide), loop.glow)
        im.alpha_composite(tint(trail.filter(ImageFilter.GaussianBlur(1.5)), loop.cream))
        im.alpha_composite(tint(core.filter(ImageFilter.GaussianBlur(1.5)), loop.white))
        return im

    # The crescent: a disc with a hole off its centre that reaches past its edge; the hole goes round. Lighter
    # inside its edge.
    outer, hole, off = loop.crescent
    shape = empty()
    draw = ImageDraw.Draw(shape)
    draw.polygon([put(mv(face, p)) for p in ring_points(outer)], fill=255)
    turn = -TAU * t
    draw.polygon([put(mv(face, p)) for p in ring_points(hole, (off * math.cos(turn), off * math.sin(turn)))], fill=0)
    part = tint(shape, loop.pale[0])
    part.alpha_composite(tint(shrink(shape, unit * 0.026), loop.pale[1]))
    parts.append((part, True))

    # The hub: two discs of gold and a dot that shines.
    for r, colour, inked in zip(loop.hub, (loop.gold[1], loop.gold[3], loop.cream), (True, True, False)):
        part = blank()
        ImageDraw.Draw(part).polygon([put(mv(face, p)) for p in ring_points(r)], fill=(*colour, 255))
        parts.append((part, inked))
    spot = empty()
    add_at(spot, soft_disc(unit * loop.hub[0] * 0.9, 0.55), *put((0.0, 0.0, 0.0)))
    parts.append((tint(spot, loop.white), False))

    # The hub and the needles share an axis; the needles cross the face of the hub.
    # The star: a long needle across and a short one up, each cut along its length into a lit and a shaded half.
    across, up, waist = loop.star
    at = lambda x, y: put(mv(face, (x, y, 0.0)))
    part = blank()
    draw = ImageDraw.Draw(part)
    for sx in (1, -1):
        for sy in (1, -1):
            draw.polygon([at(sx * across, 0), at(sx * waist, sy * waist), at(0, 0)], fill=(*(loop.pale[1] if sy > 0 else loop.gold[2]), 255))
            draw.polygon([at(0, sy * up), at(sx * waist, sy * waist), at(0, 0)], fill=(*(loop.pale[1] if sx < 0 else loop.gold[2]), 255))
    parts.append((part, True))

    # The outer ring, a band with a rectangular section: of its four sides, the ones turned to the viewer. Its faces
    # go from shade to light round the ring with two streaks of shine that sway; its walls are lit from `SUN`.
    half, tall = loop.ring
    part = blank()
    draw = ImageDraw.Draw(part)
    n = 180
    sway = math.radians(16) * math.sin(TAU * t)
    for i in range(n):
        t0, t1 = TAU * i / n, TAU * (i + 1) / n
        c, s = math.cos((t0 + t1) / 2), math.sin((t0 + t1) / 2)
        if turn_between((t0 + t1) / 2, math.radians(loop.pearl[0])) < loop.pearl[1] * 1.17:
            continue
        outward = mv(face, (c, s, 0))
        ang = math.atan2(outward[1], outward[0])
        streak = math.exp(-(turn_between(ang, math.radians(118) + sway) / math.radians(15)) ** 2) \
            + 0.7 * math.exp(-(turn_between(ang, math.radians(-55) + sway) / math.radians(10)) ** 2)
        flat_face = mix(mix(loop.gold[1], loop.gold[3], 0.5 + 0.5 * math.cos(ang - math.radians(125))), loop.shine, 0.9 * streak)
        lit = sum(x * y for x, y in zip(outward, SUN))
        walls = (
            ((c, s, 0), mix(loop.gold[0], loop.gold[2], 1.2 * lit), ((1 + half, tall, t0), (1 + half, tall, t1), (1 + half, -tall, t1), (1 + half, -tall, t0))),
            ((-c, -s, 0), mix(loop.gold[0], loop.gold[1], -1.1 * lit), ((1 - half, tall, t0), (1 - half, tall, t1), (1 - half, -tall, t1), (1 - half, -tall, t0))),
            ((0, 0, 1), flat_face, ((1 - half, tall, t0), (1 + half, tall, t0), (1 + half, tall, t1), (1 - half, tall, t1))),
            ((0, 0, -1), flat_face, ((1 - half, -tall, t0), (1 + half, -tall, t0), (1 + half, -tall, t1), (1 - half, -tall, t1))),
        )
        for normal, colour, corners in walls:
            if mv(face, normal)[2] > 0:
                # The outline in the same colour closes the hairline between neighbouring pieces.
                draw.polygon([put(mv(face, (r * math.cos(a), r * math.sin(a), h))) for r, h, a in corners],
                             fill=(*colour, 255), outline=(*colour, 255))
    parts.append((part, True))

    # The pearl set in the ring: lit from the upper left, with a white spot.
    where, r = math.radians(loop.pearl[0]), unit * loop.pearl[1]
    x, y = put(mv(face, (math.cos(where), math.sin(where), 0.0)))
    part = blank()
    draw = ImageDraw.Draw(part)
    draw.ellipse((x - r, y - r, x + r, y + r), fill=(*loop.pale[0], 255))
    draw.ellipse((x - r * 1.05, y - r * 1.05, x + r * 0.72, y + r * 0.72), fill=(*loop.cream, 255))
    draw.ellipse((x - r * 0.55, y - r * 0.6, x - r * 0.1, y - r * 0.15), fill=(*loop.white, 255))
    round_ = empty()
    ImageDraw.Draw(round_).ellipse((x - r, y - r, x + r, y + r), fill=255)
    part.putalpha(round_)
    parts.append((part, True))

    # Under everything, a glow of the metal's own outline, breathing once a loop.
    metal = empty()
    for part, inked in parts:
        if inked:
            metal = ImageChops.lighter(metal, part.getchannel("A"))
    spread, gain = loop.aura
    gain *= 0.88 + 0.12 * math.sin(TAU * t)
    out = tint(metal.filter(ImageFilter.GaussianBlur(unit * spread)).point(lambda v: min(255, round(v * gain))), loop.glow)
    out.alpha_composite(lights(sides[0]))
    for part, inked in parts:
        if inked:
            out.paste((*loop.ink, 255), (0, 0), grow(part.getchannel("A"), loop.ink_width * k))
        out.alpha_composite(part)
    out.alpha_composite(lights(sides[1]))

    # Glints: four thin points that open and close, with a glow.
    for gx, gy, when, big in loop.glints:
        u = ((t - when + loop.glint_life / 2) % 1.0) / loop.glint_life
        if not 0 < u < 1:
            continue
        wide = math.sin(math.pi * u) ** 0.8
        x, y = put(mv(face, (gx, gy, 0.0)))
        r = unit * big * wide
        spot = empty()
        add_at(spot, soft_disc(r, 0.6 * wide), x, y)
        out.alpha_composite(tint(spot, loop.glow))
        points = []
        for i in range(8):
            a = math.radians(12) * (u - 0.5) + i * math.pi / 4 - math.pi / 2
            points.append((x + r * (1.0 if i % 2 == 0 else 0.13) * math.cos(a), y + r * (1.0 if i % 2 == 0 else 0.13) * math.sin(a)))
        star = empty()
        ImageDraw.Draw(star).polygon(points, fill=255)
        out.alpha_composite(tint(star.filter(ImageFilter.GaussianBlur(1.2)), loop.white))
    return out


def armillary_frames(loop: Armillary):
    """The frames at the kept size, and where they go on the picture."""
    reach = loop.radius * 1.5
    left, top = math.floor(loop.centre[0] - reach), math.floor(loop.centre[1] - reach)
    k = loop.keep * OVER
    size = (math.ceil(2 * reach * k), math.ceil(2 * reach * k))
    drawn = [armillary_frame(loop, i / loop.frames, size, (left, top)) for i in range(loop.frames)]
    union = drawn[0].getchannel("A")
    for im in drawn[1:]:
        union = ImageChops.lighter(union, im.getchannel("A"))
    # Cut to what is drawn, leaving out the faintest edge of the glow, on whole kept pixels.
    x0, y0, x1, y1 = union.point(lambda v: 255 if v > 3 else 0).getbbox()
    x0, y0 = x0 // OVER * OVER, y0 // OVER * OVER
    x1, y1 = -(-x1 // OVER) * OVER, -(-y1 // OVER) * OVER
    frames = []
    for im in drawn:
        # Scaled down with each colour weighted by how opaque it is, so the glow's edge takes no dark fringe.
        # Where nothing is left the glow's colour is put: the colour stays smooth under the glow's edge, which
        # the lossy encoder needs.
        small = im.crop((x0, y0, x1, y1)).convert("RGBa") \
            .resize(((x1 - x0) // OVER, (y1 - y0) // OVER), Image.Resampling.LANCZOS).convert("RGBA")
        frame = Image.new("RGBA", small.size, (*loop.glow, 0))
        frame.paste(small, (0, 0), small.getchannel("A").point(lambda v: 255 if v else 0))
        frames.append(frame)
    box = tuple(round(v) for v in (left + x0 / k, top + y0 / k, left + x1 / k, top + y1 / k))
    return frames, box


def build(skin: str, loop: Flame | Armillary, source_dir: Path, preview: Path | None) -> None:
    folder = CHARACTERS / skin
    behind = isinstance(loop, Armillary)
    if isinstance(loop, Flame):
        base = Image.open(folder / "bgImage.webp").convert("RGBA")
        form = Image.open(source_dir / f"{skin}.webp").convert("RGBA")
        if base.size != form.size:
            raise SystemExit(f"{skin}: the source is {form.size}, the first picture {base.size}")
        body, frames, box = flame_frames(base, form, loop)
        body.save(folder / "formImage.webp", "WEBP", lossless=True, quality=100, method=6)
    else:
        body = Image.open(folder / "formImage.webp").convert("RGBA")
        frames, box = armillary_frames(loop)
    cw, ch = frames[0].size
    strip = Image.new("RGBA", ((cw + GAP) * loop.frames, ch), (*loop.glow, 0) if behind else (0, 0, 0, 0))
    for k, im in enumerate(frames):
        strip.paste(im, (k * (cw + GAP), 0))

    if isinstance(loop, Flame):
        # The part is painted soft, so the strip takes lossy colour with exact alpha.
        strip.save(folder / "formLoop.webp", "WEBP", quality=90, alpha_quality=100, method=6)
    else:
        # The glow needs smooth alpha, which costs most of the file kept exactly; at this quality the ink's edge
        # still shows no fringe. `exact` keeps the colour put under the clear pixels.
        strip.save(folder / "formLoop.webp", "WEBP", quality=82, alpha_quality=70, method=6, exact=True)
    # Where a frame goes on the second picture, in its pixels; the strip is the frames side by side, at any size.
    spec = {"x": box[0], "y": box[1], "w": box[2] - box[0], "h": box[3] - box[1], "frames": loop.frames, "ms": loop.ms,
            "width": body.width, "height": body.height}
    if behind:
        # Under the second picture, and coming and going with a spin and a flash instead of a fade.
        spec["behind"] = True
        spec["entrance"] = "summon"
    (folder / "formLoop.json").write_text(json.dumps(spec) + "\n")
    print(f"{skin}: {loop.frames} frames of {cw}x{ch} at {box[0]},{box[1]}, {(folder / 'formLoop.webp').stat().st_size // 1024} KB")

    if preview:
        write_preview(body, frames, box, preview, behind)


def write_preview(body: Image.Image, frames: list[Image.Image], box: tuple[int, int, int, int], path: Path,
                  behind: bool) -> None:
    """Each frame with the second picture, over it or behind it, close up at full size in rows of six, and two
    frames of the pet at 480 wide below. Room is added above the picture for frames that reach past its top."""
    pad = 30
    above = max(0, -box[1]) + pad
    cells = []
    for im in frames:
        whole = Image.new("RGBA", (body.width, body.height + above), (126, 196, 132, 255))
        im = im.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
        for layer, at in ((im, (box[0], box[1] + above)), (body, (0, above)))[::1 if behind else -1]:
            whole.alpha_composite(layer, at)
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
