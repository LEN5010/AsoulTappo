#!/usr/bin/env python3
"""Bake the key visual of a series into the pictures its page stands on.

    PHOTOCARDS=<working directory> python scripts/photocards/stage.py [depth]

Reads src/kv/ of the working directory: clean/poster.jpg is the key visual without its lettering, mask.png the members
and what stands with them, white on black at any size of the same shape (lift.swift cuts it on a Mac). Writes
client/src/assets/photocards/<series>/stage/:
  0.webp to 4.webp   the key visual from sharp, the members in focus, to the blur it has behind the box: the farther
                     from the lens' distance, the wider each thing is spread, so the page pulls focus by crossing over
                     from one to the next
  depth.webp         how near everything is, white the nearest, by which it moves as the page is looked at from aside
and the event's title as title.webp beside it, from src/logo-title.png (logo.py). With `depth` it writes depth.webp
alone.

The depth is made so that each member moves as one piece: the picture is divided among them along its edges, from
strokes drawn along each (STROKES); each has its own depth, which changes slowly across it (NEAR). Where two meet and
their depths differ much, the farther one gives way next to the nearer, so a hand never bends with what lies behind
it; where they differ little, the two are blended. The stage next to them moves with them for HALO pixels and then
gives way to its own depth, as little steeply as it can.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path(os.environ["PHOTOCARDS"])
SERIES = "asoul2026"
OUT = ROOT / "client/src/assets/photocards" / SERIES / "stage"

#: Everything below is measured at this size.
W, H = 1600, 900
#: The radius the stage behind, the members and what stands before them are spread by in each picture, how wide the
#: picture is kept, and its quality.
LENS = [(0, 0, 0, 2048, 86), (3, 1.6, 2.6, 1440, 80), (8, 4, 6.5, 1120, 80), (16, 7.5, 11.5, 896, 82), (27, 12, 18, 800, 84)]
#: What stands nearer than the members: the camera at the left, the silhouette at the right edge.
FRONT = [
    [(0, 266), (36, 268), (58, 290), (92, 306), (104, 344), (104, 398), (78, 440), (84, 474), (60, 490), (30, 492), (18, 500),
     (64, 620), (110, 730), (160, 900), (112, 900), (64, 760), (40, 690), (46, 900), (0, 900)],
    [(1500, 184), (1520, 196), (1566, 196), (1600, 180), (1600, 900), (1520, 900), (1508, 760), (1524, 640), (1560, 560),
     (1560, 470), (1520, 410), (1502, 300)],
]
#: What moves as one piece; the stage first, what stands before the members last.
PARTS = ["stage", "bella", "eileen", "diana", "bear", "props", "front"]
#: Lines along each part, from which the picture is divided among them.
STROKES = {
    "bella": [
        [(240, 170), (260, 260)], [(200, 140), (300, 120)], [(205, 175), (215, 230)],
        [(300, 125), (350, 155), (420, 230), (470, 300), (520, 370), (555, 415)],
        [(270, 290), (285, 470)], [(330, 310), (430, 410), (380, 480)], [(205, 310), (215, 455), (120, 385)],
        [(250, 520), (240, 860)], [(330, 520), (340, 860)], [(108, 335), (120, 412)],
        [(200, 430), (60, 470)], [(110, 520), (60, 600)],
    ],
    "eileen": [
        [(660, 170), (710, 260)], [(630, 150), (760, 150)], [(700, 300), (720, 470)],
        [(610, 300), (560, 420), (480, 520), (440, 560)], [(800, 370), (840, 320), (848, 298)],
        [(790, 400), (900, 430), (990, 465)], [(640, 340), (700, 390), (775, 410)],
        [(700, 480), (760, 600)], [(700, 620), (720, 860)], [(760, 620), (780, 860)], [(560, 540), (480, 600)],
    ],
    "diana": [
        [(1150, 150), (1250, 230)], [(1060, 110), (1045, 200), (960, 280), (910, 308)], [(940, 330), (1080, 325)],
        [(1200, 320), (1270, 580)], [(1330, 230), (1420, 330)], [(1100, 620), (1350, 850)],
        [(1100, 260), (1000, 420), (920, 540), (880, 650), (880, 760)], [(1430, 230), (1490, 400), (1500, 600), (1460, 700)],
        [(1050, 60), (1150, 35), (1250, 50), (1320, 110), (1345, 175)], [(1040, 40), (1085, 85)], [(1235, 60), (1275, 75)],
        [(1330, 150), (1400, 230)], [(1110, 120), (1180, 90)],
    ],
    "bear": [[(70, 270), (170, 300)], [(110, 330), (40, 420)]],
    "props": [[(440, 700), (520, 700), (640, 780)], [(440, 760), (560, 860)]],
}
#: Lines along fingers, thin to stay on them; what they cross belongs to the part even where the mask is faint.
FINE = {
    "eileen": [[(856, 298), (843, 274)], [(846, 300), (835, 288)], [(864, 298), (880, 285), (891, 278)]],
}
#: How near each part is, at points of it: x, y, 0 to 1. A part changes slowly between its points (SPREAD).
NEAR = {
    "bella": [(245, 215, .52), (285, 360, .55), (280, 520, .57), (250, 720, .56), (330, 860, .56), (500, 300, .42),
              (560, 420, .40), (370, 480, .60), (110, 520, .50), (60, 600, .50)],
    # Her hair toward Diana's is as near as Diana's own there, so the strands that cross do not tear.
    "eileen": [(685, 220, .44), (710, 400, .47), (720, 560, .48), (750, 740, .47), (865, 295, .56), (900, 430, .52),
               (560, 540, .43), (480, 600, .42), (470, 470, .44), (1000, 470, .58)],
    "diana": [(1200, 180, .78), (1080, 110, .86), (1060, 190, .84), (905, 320, .72), (1000, 340, .78), (1260, 430, .76),
              (1260, 560, .76), (1230, 740, .82), (1120, 860, .84), (1330, 230, .84), (1420, 330, .80), (900, 640, .64),
              (960, 520, .64), (870, 770, .66), (1480, 480, .62), (1500, 230, .60), (1440, 700, .66)],
    "bear": [(110, 330, .36), (40, 420, .36)],
    "props": [(520, 700, .26), (640, 780, .28), (440, 760, .30), (560, 860, .28)],
}
SPREAD = 150
#: Parts whose depths differ by less than this where they meet are blended over SOFT pixels to each side.
SEAM, SOFT = 0.14, 6
#: Where a part meets a nearer one, its own pixels give way over this many pixels; more next to the front.
GIVE, GIVE_FRONT = 16, 32
#: The stage this close to a part moves with it; farther, it gives way to its own depth over RAMP pixels.
HALO, RAMP = 6, 40
#: The size depth.webp is kept at.
DEPTH_SIZE = (800, 450)


def linear(a: np.ndarray) -> np.ndarray:
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4).astype(np.float32)


def encoded(a: np.ndarray) -> np.ndarray:
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def iris(r: float, blades: int = 7) -> np.ndarray:
    """What a point of light becomes: a disc, a little seven-sided, a little brighter at its edge."""
    n = int(np.ceil(r)) + 1
    y, x = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    at, far = np.arctan2(y, x), np.hypot(x, y)
    side = np.cos(np.pi / blades) / np.cos((at + .3) % (2 * np.pi / blades) - np.pi / blades)
    disc = np.clip(r * (.55 * side + .45) - far + .5, 0, 1) * (.82 + .18 * np.clip(far / r, 0, 1) ** 3)
    return (disc / disc.sum()).astype(np.float32)


def spread(a: np.ndarray, r: float) -> np.ndarray:
    return a if r <= 0 else cv2.filter2D(a, -1, iris(r), borderType=cv2.BORDER_REPLICATE)


def lens(a: np.ndarray, r: float, lights: float = 13) -> np.ndarray:
    """The picture out of focus. Lights outweigh what is around them, so they open into discs of their own."""
    if r <= 0:
        return a
    weight = 1 + lights * np.clip((a.max(-1, keepdims=True) - .55) / .45, 0, 1) ** 2
    return spread(a * weight, r) / spread(weight[..., 0], r)[..., None]


def filled(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """What is behind the mask, made up from around it: only ever seen far out of focus."""
    hole = cv2.dilate((mask > .03).astype(np.uint8), np.ones((13, 13), np.uint8))
    far, label = cv2.distanceTransformWithLabels(hole, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    clear = np.argwhere(hole == 0)
    order = np.zeros(label.max() + 1, np.int64)
    order[label[clear[:, 0], clear[:, 1]]] = np.arange(len(clear))
    near = clear[order[label]]
    out = a[near[..., 0], near[..., 1]]
    t = np.clip(far / 40, 0, 1)[..., None]
    return out * (1 - t) + cv2.GaussianBlur(out, (0, 0), 26) * t


def fit(image: Image.Image, w: int) -> Image.Image:
    return image.resize((w, round(w * H / W)), Image.LANCZOS)


def parts(kv: np.ndarray, group: np.ndarray) -> np.ndarray:
    """Which part each pixel belongs to (its index in PARTS): flooded from the strokes along the picture's edges, a
    member only where the mask has it."""
    front = np.zeros((H, W), np.uint8)
    for points in FRONT:
        cv2.fillPoly(front, [np.array(points, np.int32)], 1)
    seeds = np.zeros((H, W), np.int32)
    seeds[(cv2.erode((group < 0.1).astype(np.uint8), np.ones((5, 5), np.uint8)) & (1 - front)) > 0] = 1
    seeds[cv2.erode(front, np.ones((7, 7), np.uint8)) > 0] = PARTS.index("front") + 1
    for name, lines in STROKES.items():
        for points in lines:
            cv2.polylines(seeds, [np.array(points, np.int32)], False, PARTS.index(name) + 1, 7)
    fine = np.zeros((H, W), np.int32)
    for name, lines in FINE.items():
        for points in lines:
            cv2.polylines(fine, [np.array(points, np.int32)], False, PARTS.index(name) + 1, 2)
    seeds = np.where(fine > 0, fine, seeds)
    flooded = cv2.watershed(np.ascontiguousarray(cv2.GaussianBlur(kv, (0, 0), 1.2)[..., ::-1]), seeds)
    # The lines between (-1) go to a neighbour.
    out = np.where(flooded < 1, 0, flooded).astype(np.uint8)
    out = np.where(out == 0, cv2.dilate(out, np.ones((3, 3), np.uint8)), out).astype(np.int32) - 1
    out[(group < 0.5) & (out != PARTS.index("front"))] = 0
    out[fine > 0] = fine[fine > 0] - 1
    out[front > 0] = PARTS.index("front")
    return out


def blend(points: list[tuple[int, int, float]]) -> np.ndarray:
    """A part's depth everywhere: its points, each weighing less the farther away it is."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    total, sum_ = np.zeros((H, W), np.float32), np.zeros((H, W), np.float32)
    for px, py, v in points:
        d2 = (x - px) ** 2 + (y - py) ** 2
        k = np.exp(-d2 / (2 * SPREAD ** 2)) + 1e-6 / (d2 + 1)
        total += k
        sum_ += k * v
    return sum_ / total


def least_steep(u: np.ndarray, free: np.ndarray, steps: int) -> np.ndarray:
    """The free pixels filled in from the rest as little steeply as can be: each the mean of its highest and lowest
    neighbour, over and over."""
    k = np.ones((3, 3), np.uint8)
    u = u.copy()
    for _ in range(steps):
        v = 0.5 * (cv2.dilate(u, k) + cv2.erode(u, k))
        u[free] = v[free]
    return u


def fill(u: np.ndarray, free: np.ndarray) -> np.ndarray:
    """least_steep() at an eighth of the size first, then at each size up from there."""
    sizes = [(u, free)]
    for _ in range(3):
        a, f = sizes[-1]
        h, w = a.shape
        sizes.append((cv2.resize(a, (w // 2, h // 2), interpolation=cv2.INTER_AREA),
                      cv2.resize(f.astype(np.uint8), (w // 2, h // 2), interpolation=cv2.INTER_NEAREST) > 0))
    out = None
    for a, f in reversed(sizes):
        start = a.copy()
        if out is not None:
            up = cv2.resize(out, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
            start[f] = up[f]
        out = least_steep(start, f, 400 if out is None else 160)
    return out


def within(seeds: np.ndarray, region: np.ndarray, steps: int) -> np.ndarray:
    """What of [region] lies within [steps] pixels of [seeds] without leaving it."""
    k = np.ones((3, 3), np.uint8)
    out = (seeds & region).astype(np.uint8)
    inside = region.astype(np.uint8)
    for _ in range(steps):
        out = cv2.dilate(out, k) & inside
    return out > 0


def depth_map(kv: np.ndarray, group: np.ndarray) -> np.ndarray:
    """How near everything is, at W by H."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    # The stage: a little nearer toward its floor and at its pillars.
    stage = .03 + .13 * np.clip((y - 300) / 600, 0, 1)
    for x0, x1, v in [(775, 882, .20), (1366, 1422, .22)]:
        stage = np.maximum(stage, v * np.clip((x - x0) / 8, 0, 1) * np.clip((x1 - x) / 8, 0, 1))
    part = parts(kv, group)
    member = part > 0
    front = part == PARTS.index("front")
    own = np.full((H, W), -1, np.float32)
    for name, points in NEAR.items():
        at = part == PARTS.index(name)
        own[at] = blend(points)[at]
    own[front] = 1
    # Where parts meet: the farther gives way next to a nearer one; two about as near are blended.
    k3 = np.ones((3, 3), np.uint8)
    by_front = cv2.dilate(front.astype(np.uint8), k3) > 0
    under, under_front, seam = (np.zeros((H, W), bool) for _ in range(3))
    for i in range(1, len(PARTS)):
        at = part == i
        other = member & ~at
        most = cv2.dilate(np.where(other, own, -1).astype(np.float32), k3)
        least = -cv2.dilate(np.where(other, -own, -2).astype(np.float32), k3)
        touch = at & (most > -1)
        nearer = touch & (most >= own + SEAM)
        under_front |= nearer & by_front & ~front
        under |= nearer & ~by_front
        seam |= touch & ~nearer & (own - least < SEAM)
    give = np.zeros((H, W), bool)
    for i in range(1, len(PARTS)):
        at = part == i
        give |= within(under_front, at, GIVE_FRONT) | within(under, at, GIVE)
    soft = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * SOFT + 1, 2 * SOFT + 1))
    give |= (cv2.dilate(seam.astype(np.uint8), soft) > 0) & member
    give &= ~front
    # The stage next to a part moves with the nearest one there, then gives way.
    halo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * HALO + 1, 2 * HALO + 1))
    reach = cv2.dilate(own, halo)
    held = member | (reach >= 0)
    depth = np.where(member, own, np.where(reach >= 0, reach, stage)).astype(np.float32)
    far = cv2.distanceTransform((~held).astype(np.uint8), cv2.DIST_L2, 5)
    depth = fill(depth, (~held & (far < RAMP)) | give)
    # Softened by a pixel, so the edge where one covers another does not come out in steps.
    return cv2.GaussianBlur(depth, (0, 0), 1.0)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    poster = Image.open(WORK / "src/kv/clean/poster.jpg").convert("RGB")
    # A row or two more than 16:9.
    w = poster.width
    h = round(w * H / W)
    top = (poster.height - h) // 2
    poster = poster.crop((0, top, w, top + h))
    mask = Image.open(WORK / "src/kv/mask.png").convert("L").resize((W, H), Image.LANCZOS)
    group = np.asarray(mask).astype(np.float32) / 255
    kv = np.asarray(poster.resize((W, H), Image.LANCZOS))
    only_depth = sys.argv[1:] == ["depth"]

    if not only_depth:
        pic = linear(kv.astype(np.float32) / 255)
        front = np.zeros((H, W), np.float32)
        for points in FRONT:
            cv2.fillPoly(front, [np.array(points, np.int32)], 1, cv2.LINE_AA)
        front = cv2.GaussianBlur(front, (0, 0), 3)
        back = filled(pic, np.maximum(group, front))
        for i, (far, mid, near, width, quality) in enumerate(LENS):
            if not mid:
                out = fit(poster, width)
            else:
                a = spread(group, mid)[..., None]
                all_ = lens(back, far) * (1 - a) + lens(pic * group[..., None], mid, 0)
                f = spread(front, near)[..., None]
                all_ = all_ * (1 - f) + lens(pic * front[..., None], near, 0)
                out = fit(Image.fromarray((encoded(all_) * 255).round().astype(np.uint8)), width)
            out.save(OUT / f"{i}.webp", "WEBP", quality=quality, method=6)

    depth = cv2.resize(depth_map(kv, group), DEPTH_SIZE, interpolation=cv2.INTER_AREA)
    # Lossless: the blocks of a lossy one would make what is in them move by steps.
    Image.fromarray((np.clip(depth, 0, 1) * 255).round().astype(np.uint8)).save(OUT / "depth.webp", "WEBP", lossless=True,
                                                                                quality=100, method=6)
    if not only_depth:
        title = Image.open(WORK / "src/logo-title.png")
        title.save(OUT.parent / "title.webp", "WEBP", quality=90, alpha_quality=100, method=6)
    for f in [*sorted(OUT.glob("*.webp")), OUT.parent / "title.webp"]:
        print(f"{f.name:12} {f.stat().st_size:8} {Image.open(f).size}")


if __name__ == "__main__":
    main()
