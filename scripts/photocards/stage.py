#!/usr/bin/env python3
"""Bake the key visual of a series into the pictures its page stands on.

    PHOTOCARDS=<working directory> python scripts/photocards/stage.py

Reads src/kv/ of the working directory: clean/poster.jpg is the key visual without its lettering, mask.png the members
and what stands with them, white on black at any size of the same shape (lift.swift cuts it on a Mac), and plates/ (or
the directory PLATES names): what is hidden behind what stands in front, painted (image_gen), each the part of the key
visual named in PLATES with what is in front taken away. Writes client/src/assets/photocards/<series>/stage/:
  0.webp to 4.webp       the key visual from sharp, the members in focus, to the blur it has behind the box: the
                         farther from the lens' distance, the wider each thing is spread, so the page pulls focus by
                         crossing over from one to the next. They are shown as they are while nothing moves.
  stage-0 to 4.webp      the stage alone in each, what is hidden behind the rest painted or made up
  layers-0 to 4.webp     the pieces standing on it, cut out and laid side by side on a sheet, their colour multiplied by
                         how much of each place they cover
  cover-0 to 4.webp      how much they cover, on the same sheet
  depth.webp             how near the stage (red), the members beside Diana (green) and Diana (blue) are, white the
                         nearest; each changes slowly
  layout.json            where each piece lies in the picture and on the sheet, and how near it is
and the event's title as title.webp beside it, from src/logo-title.png (logo.py).

The picture is divided into pieces that each move as one (LAYERS): the stage, the alpaca behind Bella, the members
beside Diana with the props among them, Diana, and what stands before them. What the mask leaves out of them is added
to it (MORE). The picture is divided among the members along strokes drawn along each (STROKES); each has its own
depth, which changes slowly across it (NEAR). What stands before them is what is darkest within their outlines (FRONT).
Each piece reaches on under the ones before it, as far as they can move aside, and holds there what they hide: painted
where there is a plate for it, else made up from around. Laid over each other again, as they are while nothing moves,
they make the key visual, and 1.webp to 4.webp are made of them so.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path(os.environ["PHOTOCARDS"])
PLATES_AT = Path(os.environ.get("PLATES") or WORK / "src/kv/plates")
SERIES = "asoul2026"
OUT = ROOT / "client/src/assets/photocards" / SERIES / "stage"

#: Everything below is measured at this size.
W, H = 1600, 900
#: The radius the stage behind, the members and what stands before them are spread by in each picture, how wide the
#: picture is kept, and its quality.
LENS = [(0, 0, 0, 2048, 86), (3, 1.6, 2.6, 1440, 80), (8, 4, 6.5, 1120, 80), (16, 7.5, 11.5, 896, 82), (27, 12, 18, 800, 84)]
#: The quality of the stage alone and of the sheets of pieces, and of how much they cover where that is out of focus;
#: in focus it is kept whole, for its edges.
QUALITY, COVER_QUALITY = 80, 90
#: Around what stands nearer than the members: the camera and its stand at the left, the silhouette at the right edge.
#: Within these, what is darkest is theirs. Each with how dark it may be within its outline alone (as DARK), and
#: whether the members' mask beside it is never its own.
FRONT = [
    # The camera is dark blue as much as black, against the light alpaca and Bella.
    ([(0, 266), (36, 268), (58, 290), (92, 306), (104, 344), (104, 398), (78, 440), (84, 474), (60, 490), (30, 492),
      (18, 500), (0, 500)], (0.30, 0.22), False),
    # Its stand is against the dark floor.
    ([(0, 490), (30, 492), (18, 500), (64, 620), (110, 730), (160, 900), (112, 900), (64, 760), (40, 690), (46, 900),
      (0, 900)], None, False),
    ([(1500, 184), (1520, 196), (1566, 196), (1600, 180), (1600, 900), (1520, 900), (1508, 760), (1524, 640), (1560, 560),
      (1560, 470), (1520, 410), (1502, 300)], None, True),
]
#: Its brightest channel, 0 to 1, at which it begins to be theirs and at which it is wholly theirs.
DARK = (0.12, 0.05)
#: What is lighter within them is theirs too, their highlights: what the dark closes around once gaps in it narrower
#: than twice this are bridged.
GAP = 10
#: How near they are.
FRONT_NEAR = 0.8
#: The parts the picture is divided into; the stage first, what stands before the members last.
PARTS = ["stage", "bella", "eileen", "diana", "bear", "props", "front"]
#: Lines along each part, from which the picture is divided among them. Where two cross, the later one's part holds.
STROKES = {
    "bella": [
        [(240, 170), (260, 260)], [(200, 140), (300, 120)], [(205, 175), (215, 230)],
        [(300, 125), (350, 155), (420, 230), (470, 300), (520, 370), (555, 415)],
        [(270, 290), (285, 470)], [(330, 310), (430, 410), (380, 480)], [(205, 310), (215, 455), (120, 385)],
        [(250, 520), (240, 860)], [(330, 520), (340, 860)], [(200, 430), (60, 470)],
        # The microphone in her hand, from its head down its handle.
        [(66, 278), (90, 315), (108, 335), (120, 412)],
        # The belt left of the pouch, from its pointed end up through the buckle.
        [(228, 522), (229, 512), (235, 502), (248, 494), (266, 486)],
        # The ponytail's strands that are as dark as the stage behind them: the outermost, round the stage that shows
        # within it and down, and those below it.
        [(435, 152), (470, 160), (500, 164), (520, 170), (533, 177), (539, 188), (539, 205), (536, 220), (525, 240),
         (517, 260)],
        [(478, 222), (500, 240), (520, 258)], [(534, 258), (549, 274), (563, 292)],
    ],
    "eileen": [
        [(660, 170), (710, 260)], [(630, 150), (760, 150)], [(700, 300), (720, 470)],
        [(610, 300), (560, 420), (480, 520), (440, 560)], [(800, 370), (840, 320), (848, 298)],
        [(790, 400), (900, 430), (990, 465)], [(640, 340), (700, 390), (775, 410)],
        [(700, 480), (760, 600)], [(700, 620), (720, 860)], [(760, 620), (780, 860)], [(560, 540), (480, 600)],
        [(812, 470), (825, 500), (830, 520)],
    ],
    "diana": [
        [(1150, 150), (1250, 230)], [(1060, 110), (1045, 200), (960, 280), (910, 308)], [(940, 330), (1080, 325)],
        [(1200, 320), (1270, 580)], [(1330, 230), (1420, 330)], [(1100, 620), (1350, 850)],
        [(1100, 260), (1000, 420), (920, 540), (880, 650), (880, 760)], [(1430, 230), (1490, 400), (1500, 600), (1460, 700)],
        [(1050, 60), (1150, 35), (1250, 50), (1320, 110), (1345, 175)], [(1040, 40), (1085, 85)], [(1235, 60), (1275, 75)],
        [(1330, 150), (1400, 230)], [(1110, 120), (1180, 90)],
    ],
    # The alpaca behind her arm: its head, its face beside her hand, its side, the strip of it between her arm and her
    # hair, and below her hair the rest of it with the bottle lying on it, up to the end of her belt.
    "bear": [[(100, 255), (165, 290)], [(106, 284), (111, 300), (117, 316), (122, 328), (124, 345), (124, 356)],
             [(150, 330), (175, 390)], [(90, 427), (180, 433)], [(95, 565), (185, 515)], [(50, 575), (90, 620), (160, 640)],
             [(213, 503), (214, 518), (213, 530)]],
    "props": [[(440, 700), (520, 700), (640, 780)], [(440, 760), (560, 860)]],
}
#: Lines along fingers, thin to stay on them; what they cross belongs to the part even where the mask is faint.
FINE = {
    "eileen": [[(856, 298), (843, 274)], [(846, 300), (835, 288)], [(864, 298), (880, 285), (891, 278)]],
}
#: What the mask leaves out or the strokes do not reach, with the part it belongs to: outlines (width 0) and paths as
#: wide as given, each fitted to the edges within BAND of it.
MORE = {
    # The bow on her head, with the fingers before it.
    "diana": [([(1026, 52), (1040, 42), (1060, 33), (1080, 28), (1092, 26), (1087, 0), (1248, 0), (1250, 18),
                (1230, 26), (1160, 30), (1120, 40), (1100, 55), (1085, 70), (1072, 85), (1066, 86), (1050, 72),
                (1036, 60)], 0)],
    # The chain from her belt, and the length of it that hangs to the floor.
    "bella": [([(269, 512), (260, 517), (250, 524), (240, 530), (230, 535), (220, 540), (210, 544), (200, 550),
                (190, 556), (184, 561), (179, 566)], 9),
              ([(225, 542), (220, 552), (215, 565), (210, 577), (203, 590), (195, 600), (188, 607), (175, 616),
                (165, 621), (155, 625), (150, 626)], 9),
              # The tip of the red ornament on her head.
              ([(246, 70), (250, 72), (254, 74), (258, 76)], 5)],
}
BAND = 3
#: How near each part is, at points of it: x, y, 0 to 1. A part changes slowly between its points (SPREAD).
NEAR = {
    "bella": [(245, 215, .52), (285, 360, .55), (280, 520, .57), (250, 720, .56), (330, 860, .56), (500, 300, .42),
              (560, 420, .40), (370, 480, .60), (110, 465, .50)],
    # Her hair toward Diana's is nearly as near as Diana's own there, so the strands that cross hardly tear.
    "eileen": [(685, 220, .44), (710, 400, .47), (720, 560, .48), (750, 740, .47), (865, 295, .56), (900, 430, .52),
               (560, 540, .43), (480, 600, .42), (470, 470, .44), (1000, 470, .58)],
    "diana": [(1200, 180, .78), (1080, 110, .86), (1060, 190, .84), (905, 320, .72), (1000, 340, .78), (1260, 430, .76),
              (1260, 560, .76), (1230, 740, .82), (1120, 860, .84), (1330, 230, .84), (1420, 330, .80), (900, 640, .64),
              (960, 520, .64), (870, 770, .66), (1480, 480, .62), (1500, 230, .60), (1440, 700, .66)],
    # As near as Eileen's hair over the alpaca among them, so its ears and the strands move with it.
    "props": [(520, 640, .42), (440, 800, .40)],
}
SPREAD = 150
#: What moves as one, from the back after the stage: its parts, and how near it is where that is the same all over it
#: (else the channel of depth.webp that has it).
LAYERS = [("bear", ["bear"], 0.32), ("members", ["bella", "eileen", "props"], "g"), ("diana", ["diana"], "b"),
          ("front", ["front"], FRONT_NEAR)]
#: How far each piece reaches on under those before it, in pixels: as far as they move aside from it at the most, and as
#: far again as either is spread.
REACH = {"bear": 48, "members": 48, "diana": 44}
#: Pictures of what is hidden, painted: the file in PLATES_AT and the part of the picture it shows (x0, y0, x1, y1), for
#: the piece it is named after. What it shows besides that piece is taken from it only where it shows that piece.
PLATES = {
    "stage": ("stage.png", (0, 0, W, H)),
}
#: How far from what shows of the stage what is hidden of it may be as bright as that, in pixels.
LAMP = 24
#: Of a pixel, less than this of a part is none of it.
EDGE = 0.02
#: The pieces lie on their sheet this far apart, and where they lie is a multiple of it, so that it is a whole number of
#: pixels at every size the pictures are kept at. The sheet is this wide.
STEP, SHEET_W = 50, 1600


def linear(a: np.ndarray) -> np.ndarray:
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4).astype(np.float32)


def encoded(a: np.ndarray) -> np.ndarray:
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def as_bytes(a: np.ndarray) -> np.ndarray:
    return (encoded(a) * 255).round().astype(np.uint8)


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


def fit(image: Image.Image, w: int) -> Image.Image:
    return image.resize((w, round(w * H / W)), Image.LANCZOS)


def disk(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def sized(a: np.ndarray, w: int, h: int) -> np.ndarray:
    if a.shape[1] == w and a.shape[0] == h:
        return a
    return cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA if w < a.shape[1] else cv2.INTER_LINEAR)


def front_cover(kv: np.ndarray, group: np.ndarray) -> np.ndarray:
    """How much of each pixel the things before the members cover: what is dark within their outlines, whole inside
    with the highlights it closes around, its edge softened over about a pixel. Told by colour instead, what is dark
    beside it would be partly its own."""
    bright = kv.max(-1).astype(np.float32) / 255
    dark = np.clip((DARK[0] - bright) / (DARK[0] - DARK[1]), 0, 1)
    out = np.zeros((H, W), np.float32)
    for points, deep, apart in FRONT:
        outline = np.zeros((H, W), np.uint8)
        cv2.fillPoly(outline, [np.array(points, np.int32)], 1)
        near = cv2.dilate(outline, disk(12)) > 0
        a = dark * near
        if deep:
            a = np.maximum(a, np.clip((deep[0] - bright) / (deep[0] - deep[1]), 0, 1) * outline)
        if apart:
            a *= 1 - group
        whole = cv2.morphologyEx((a >= .5).astype(np.uint8), cv2.MORPH_CLOSE, disk(2))
        # Its inside: the dark with its gaps bridged, and what that closes around, not reached from beyond the outline.
        # The picture's edge does not count as beyond, for it stands across it.
        shut = cv2.morphologyEx(whole, cv2.MORPH_CLOSE, disk(GAP))
        free = (shut == 0).astype(np.uint8)
        _, lab = cv2.connectedComponents(free, connectivity=4)
        inside = (shut > 0) | ((free > 0) & ~np.isin(lab, np.unique(lab[(free > 0) & ~near])))
        inside = cv2.erode(inside.astype(np.uint8), disk(2)) > 0
        if apart:
            inside &= group < .5
        core = ((whole > 0) | inside).astype(np.uint8)
        a = np.where(cv2.erode(core, disk(1)) > 0, 1, cv2.GaussianBlur(core.astype(np.float32), (0, 0), .8) * near)
        if apart:
            a *= 1 - group
        out = np.maximum(out, a)
    return out


def added(kv: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The mask with MORE added to it, and the part each place added belongs to (-1 where none). Of an outline, what is
    well inside it, and near its edge what looks like it rather than like what is around (grabCut). Along a path, what
    stands out from what is around it: a wide median leaves out what is thin."""
    group, extra = group.copy(), np.full((H, W), -1, np.int32)
    ground = cv2.medianBlur(kv, 21).astype(np.float32)
    stands_out = (np.linalg.norm(kv.astype(np.float32) - ground, axis=-1) > 28).astype(np.uint8)
    for name, items in MORE.items():
        for points, width in items:
            rough = np.zeros((H, W), np.uint8)
            if width:
                cv2.polylines(rough, [np.array(points, np.int32)], False, 1, width)
                fit = cv2.morphologyEx(rough & stands_out, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                fit = cv2.dilate(fit, np.ones((3, 3), np.uint8)) & rough
            else:
                cv2.fillPoly(rough, [np.array(points, np.int32)], 1)
                sure, around = cv2.erode(rough, disk(BAND)), cv2.dilate(rough, disk(BAND))
                label = np.select([sure > 0, rough > 0, around > 0], [cv2.GC_FGD, cv2.GC_PR_FGD, cv2.GC_PR_BGD],
                                  cv2.GC_BGD).astype(np.uint8)
                ys, xs = np.nonzero(around)
                m = 6 * BAND
                y0, y1 = max(ys.min() - m, 0), min(ys.max() + m + 1, H)
                x0, x1 = max(xs.min() - m, 0), min(xs.max() + m + 1, W)
                box = np.ascontiguousarray(label[y0:y1, x0:x1])
                cv2.setRNGSeed(0)
                cv2.grabCut(np.ascontiguousarray(kv[y0:y1, x0:x1, ::-1]), box, None, np.zeros((1, 65)),
                            np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_MASK)
                fit = np.zeros((H, W), np.uint8)
                fit[y0:y1, x0:x1] = (box == cv2.GC_FGD) | (box == cv2.GC_PR_FGD)
            group = np.maximum(group, cv2.GaussianBlur(fit.astype(np.float32), (0, 0), .7))
            extra[fit > 0] = PARTS.index(name)
    return group, extra


def parts(kv: np.ndarray, group: np.ndarray, front: np.ndarray, extra: np.ndarray) -> np.ndarray:
    """Which part each pixel belongs to (its index in PARTS): what stands before the members where it covers most of
    a pixel; the rest flooded from the strokes along the picture's edges, a member only where the mask has it, and what
    MORE adds as it says."""
    whole = front >= .5
    seeds = np.zeros((H, W), np.int32)
    seeds[(cv2.erode((group < 0.1).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~whole] = 1
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
    out[group < 0.5] = 0
    out[fine > 0] = fine[fine > 0] - 1
    out[extra >= 0] = extra[extra >= 0]
    out[whole] = PARTS.index("front")
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


def coverage(part: np.ndarray, group: np.ndarray, front: np.ndarray) -> np.ndarray:
    """How much of each pixel each part covers, by part: the members share the mask along the lines between them, what
    stands before them has its own, and the stage has what is left."""
    n, last = len(PARTS), PARTS.index("front")
    cov = np.zeros((n, H, W), np.float32)
    share = np.stack([cv2.GaussianBlur((part == i).astype(np.float32), (0, 0), .7) for i in range(1, last)])
    total = share.sum(0)
    cov[1:last] = np.clip(group, 0, 1) * (1 - front) * np.where(total > 1e-3, share / np.maximum(total, 1e-3), 0)
    cov[last] = front
    cov[0] = np.clip(1 - cov[1:].sum(0), 0, 1)
    return cov


def nearness(part: np.ndarray) -> np.ndarray:
    """How near the stage, the members beside Diana (with the props among them) and Diana are, everywhere (H, W, 3). The
    stage is a little nearer toward its floor and at its pillars; the members' depths run into each other where they
    meet."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    stage = .03 + .13 * np.clip((y - 300) / 600, 0, 1)
    for x0, x1, v in [(775, 882, .20), (1366, 1422, .22)]:
        stage = np.maximum(stage, v * np.clip((x - x0) / 8, 0, 1) * np.clip((x1 - x) / 8, 0, 1))
    stage = cv2.GaussianBlur(stage, (0, 0), 6)
    num, den = np.zeros((H, W), np.float32), np.full((H, W), 1e-6, np.float32)
    for name in ["bella", "eileen", "props"]:
        w = cv2.GaussianBlur((part == PARTS.index(name)).astype(np.float32), (0, 0), 10) + 1e-6
        num += w * blend(NEAR[name])
        den += w
    return np.stack([stage, num / den, blend(NEAR["diana"])], -1).astype(np.float32)


def made_up(colour: np.ndarray, known: np.ndarray) -> np.ndarray:
    """[colour] where it is not [known], made up from where it is: what is known spread out, the nearer the more."""
    k = known.astype(np.float32)
    levels = [(colour * k[..., None] if colour.ndim == 3 else colour * k, k)]
    while min(levels[-1][1].shape) > 4:
        c, w = levels[-1]
        levels.append((cv2.pyrDown(c), cv2.pyrDown(w)))
    out = None
    for c, w in reversed(levels):
        ww = np.maximum(w, 1e-6)
        mean = c / (ww[..., None] if c.ndim == 3 else ww)
        if out is not None:
            up = cv2.resize(out, (c.shape[1], c.shape[0]), interpolation=cv2.INTER_LINEAR)
            t = np.clip(w * 3, 0, 1)
            mean = mean * (t[..., None] if c.ndim == 3 else t) + up * (1 - (t[..., None] if c.ndim == 3 else t))
        out = mean
    return np.where(known[..., None] if colour.ndim == 3 else known, colour, out).astype(np.float32)


def soft_mean(a: np.ndarray, known: np.ndarray, sigma: float) -> np.ndarray:
    """The mean of [a] around each place, of where it is known."""
    k = cv2.GaussianBlur(known.astype(np.float32), (0, 0), sigma)
    m = cv2.GaussianBlur(a * (known[..., None] if a.ndim == 3 else known), (0, 0), sigma)
    return m / np.maximum(k, 1e-4)[..., None] if a.ndim == 3 else m / np.maximum(k, 1e-4)


def plate(name: str, kv: np.ndarray, same: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray] | None:
    """The plate [name] at [scale] times W by H, linear, and where it lies; None where there is none. It is laid onto the
    key visual where [same] says the two show the same thing, first as a whole, then place by place, and shaded as the
    key visual is there."""
    file, (x0, y0, x1, y1) = PLATES[name]
    if not (PLATES_AT / file).exists():
        return None
    painted = np.asarray(Image.open(PLATES_AT / file).convert("RGB"))
    bw, bh = x1 - x0, y1 - y0
    small = cv2.resize(painted, (bw, bh), interpolation=cv2.INTER_AREA)
    gray = lambda a: cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_RGB2GRAY)
    want, have = gray(kv[y0:y1, x0:x1]), gray(small)
    mask = same[y0:y1, x0:x1].astype(np.uint8)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(want.astype(np.float32) / 255, have.astype(np.float32) / 255, warp,
                                       cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6),
                                       mask, 5)
    except cv2.error:
        pass
    moved = cv2.warpAffine(have, warp, (bw, bh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_REPLICATE)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(want, moved, None)
    # Place by place only where the two show the same, and smoothly; carried on into what is hidden from around it.
    sure = (mask > 0) & (np.linalg.norm(flow, axis=-1) < 14)
    flow = made_up(soft_mean(flow, sure, 3), cv2.erode(sure.astype(np.uint8), disk(2)) > 0)
    # Where each pixel of the picture at [scale] takes the plate from.
    tw, th = round(bw * scale), round(bh * scale)
    u, v = np.meshgrid((np.arange(tw) + .5) / scale - .5, (np.arange(th) + .5) / scale - .5)
    u, v = u.astype(np.float32), v.astype(np.float32)
    f = cv2.remap(flow, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    pu, pv = u + f[..., 0], v + f[..., 1]
    su = (warp[0, 0] * pu + warp[0, 1] * pv + warp[0, 2] + .5) * painted.shape[1] / bw - .5
    sv = (warp[1, 0] * pu + warp[1, 1] * pv + warp[1, 2] + .5) * painted.shape[0] / bh - .5
    out = linear(cv2.remap(painted, su.astype(np.float32), sv.astype(np.float32), cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255)
    # Shaded as the key visual is: by how much brighter it is, colour by colour, around each place where both show.
    near = cv2.resize(same[y0:y1, x0:x1].astype(np.uint8), (tw, th), interpolation=cv2.INTER_NEAREST) > 0
    seen = linear(sized(kv[y0:y1, x0:x1], tw, th).astype(np.float32) / 255)
    sigma = 14 * scale
    gain = (soft_mean(seen, near, sigma) + .01) / (soft_mean(out, near, sigma) + .01)
    gain = made_up(np.clip(gain, .5, 2), cv2.GaussianBlur(near.astype(np.float32), (0, 0), sigma) > .2)
    full = np.zeros((round(H * scale), round(W * scale), 3), np.float32)
    where = np.zeros(full.shape[:2], bool)
    tx, ty = round(x0 * scale), round(y0 * scale)
    full[ty:ty + th, tx:tx + tw] = np.clip(out * gain, 0, 1)
    where[ty:ty + th, tx:tx + tw] = True
    return full, where


def pieces(poster: Image.Image, kv: np.ndarray, group: np.ndarray, extra: np.ndarray, scale: float) -> dict:
    """The pieces at [scale] times W by H as they lie while nothing moves: the stage alone (linear), and for each of
    LAYERS its colour (linear, not multiplied by how much it covers) and how much of each place it covers, reaching on
    under what is before it. Laid over each other they make the key visual."""
    front = front_cover(kv, group)
    part = parts(kv, group, front, extra)
    cov = coverage(part, group, front)
    w, h = round(W * scale), round(H * scale)
    up = lambda a: sized(a, w, h)
    picture = linear(np.asarray(fit(poster, w)).astype(np.float32) / 255) if scale != 1 else \
        linear(kv.astype(np.float32) / 255)
    names = [name for name, _, _ in LAYERS]
    shown = {name: up(sum(cov[PARTS.index(p)] for p in members)) for name, members, _ in LAYERS}
    # How much each covers of what is behind what is before it, from the front.
    left, alpha, seen = np.ones((h, w), np.float32), {}, {}
    for name in reversed(names):
        seen[name] = left > .02
        alpha[name] = np.where(seen[name], np.clip(shown[name] / np.maximum(left, 1e-6), 0, 1), 0)
        left = left * (1 - alpha[name])
    # Where each is the nearest thing there.
    before, nearest = np.zeros((h, w), np.float32), {}
    for name in reversed(names):
        nearest[name] = (shown[name] > EDGE) & (before <= EDGE)
        before = before + shown[name]
    # Under what is before it a piece covers as much as it does around that: it goes on as it was going.
    cover = {}
    for name in names:
        if name not in REACH:
            cover[name] = alpha[name]
            continue
        solid = (seen[name] & (alpha[name] >= .5)).astype(np.uint8)
        far = cv2.distanceTransform(1 - solid, cv2.DIST_L2, 5)
        on = np.clip((REACH[name] * scale - far) / (3 * scale), 0, 1)
        guess = made_up(alpha[name], seen[name])
        cover[name] = np.where(seen[name], alpha[name], np.clip((guess - .3) / .4, 0, 1) * on)
    # What the plate is laid onto the key visual by: what it shows that is not taken away.
    stage_seen = cov[0] >= 1 - EDGE
    plates = {"stage": plate("stage", kv, stage_seen, scale)}
    # The stage alone: as it is where nothing covers it; where something covers some of it, as it is around there, for
    # what shows through is that; painted, or made up, where it is hidden.
    open_ = up(stage_seen.astype(np.float32)) > .5
    if plates["stage"]:
        some = up(cov[0]) > EDGE
        # What is hidden is no brighter than the stage that shows around it: a lamp painted behind someone would come out
        # of nowhere as they move.
        bright = np.where(open_, picture.max(-1), 0).astype(np.float32)
        r = disk(round(LAMP * scale))
        top = made_up(cv2.dilate(bright, r), cv2.dilate(open_.astype(np.uint8), r) > 0)
        top = cv2.GaussianBlur(top, (0, 0), 4 * scale) + .01
        hidden = plates["stage"][0]
        hidden = hidden * np.minimum(1, top / np.maximum(hidden.max(-1), 1e-4))[..., None]
        stage = np.where(open_[..., None], picture, np.where(some[..., None], made_up(picture, open_), hidden))
    else:
        hidden = cv2.dilate((~open_).astype(np.uint8), disk(3))
        stage = linear(cv2.inpaint(np.ascontiguousarray(as_bytes(picture)[..., ::-1]), hidden, 5,
                                   cv2.INPAINT_TELEA)[..., ::-1].astype(np.float32) / 255)
        stage = np.where(open_[..., None], picture, stage)
    behind = stage
    colour = {}
    for name in names:
        # Where it is the nearest thing, it covers at least as much as it must for what the key visual shows there to be
        # it over what is behind it: the mask is often too tight at an edge.
        must = np.zeros((h, w), np.float32)
        for ch in range(3):
            b, c = behind[..., ch], picture[..., ch]
            must = np.maximum(must, np.where(c < b, (b - c) / np.maximum(b, 1e-4), (c - b) / np.maximum(1 - b, 1e-4)))
        lead = nearest[name] & (alpha[name] >= .05)
        a = np.where(lead, np.maximum(alpha[name], np.clip(must, 0, 1)), alpha[name])
        cover[name] = np.where(lead, a, cover[name])
        # There it is what the key visual shows less what shows through it; where it covers little, that is too
        # uncertain to go by.
        known = lead & (a >= .08)
        a = a[..., None]
        c = np.where(known[..., None], np.clip((picture - (1 - a) * behind) / np.maximum(a, 1e-3), 0, 1), 0)
        colour[name] = made_up(c.astype(np.float32), known)
        c = colour[name]
        k = cover[name][..., None]
        behind = k * c + (1 - k) * behind
    return {"stage": stage, "colour": colour, "cover": cover, "part": part, "picture": picture}


def laid(pieces_: dict, level: int, scale: float) -> tuple[np.ndarray, dict, dict]:
    """The pieces out of focus as in picture [level]: the stage alone (linear), and each piece multiplied by how much it
    covers, with how much that is."""
    far, mid, near, _, _ = LENS[level]
    stage = lens(pieces_["stage"], far * scale)
    lit, cover = {}, {}
    for name, _, _ in LAYERS:
        r = (near if name == "front" else mid) * scale
        k = pieces_["cover"][name]
        lit[name] = spread(pieces_["colour"][name] * k[..., None], r)
        cover[name] = spread(k, r)
    return stage, lit, cover


def together(stage: np.ndarray, lit: dict, cover: dict) -> np.ndarray:
    out = stage
    for name, _, _ in LAYERS:
        out = lit[name] + (1 - cover[name][..., None]) * out
    return out


def cutouts(cover: dict) -> list[dict]:
    """Where each piece is cut out of the picture: as far as it reaches spread at the most, out to whole STEPs; the
    things before the members as two, the camera and the silhouette. Laid on the sheet in rows."""
    cuts = []
    for name, _, deep in LAYERS:
        k = cover[name] > 1 / 255
        r = int(np.ceil(max(LENS[-1][1:3]))) + 4
        k = cv2.dilate(k.astype(np.uint8), disk(r)) > 0
        sides = [("camera", k[:, :W // 2]), ("silhouette", k[:, W // 2:])] if name == "front" else [(name, k)]
        for cut, m in sides:
            ys, xs = np.nonzero(m)
            if not len(xs):
                continue
            x_off = W // 2 if cut == "silhouette" else 0
            x0 = max(0, (xs.min() + x_off) // STEP * STEP)
            y0 = max(0, ys.min() // STEP * STEP)
            x1 = min(W, -(-(xs.max() + 1 + x_off) // STEP) * STEP)
            y1 = min(H, -(-(ys.max() + 1) // STEP) * STEP)
            near = [0, 0, 0, deep] if isinstance(deep, float) else [float(c == deep) for c in "rgb"] + [0]
            cuts.append({"name": cut, "piece": name, "box": [x0, y0, x1 - x0, y1 - y0], "near": near})
    # In rows, the tallest first.
    x = y = row = 0
    for c in sorted(cuts, key=lambda c: -c["box"][3]):
        w, h = c["box"][2:]
        if x and x + w > SHEET_W:
            x, y, row = 0, y + row + STEP, 0
        c["on"] = [x, y, w, h]
        x += w + STEP
        row = max(row, h)
    return cuts


def sheet(cuts: list[dict], planes: dict, scale: float, height: int) -> np.ndarray:
    """The pieces' [planes] (each W by H times [scale]) cut out and laid on a sheet."""
    first = next(iter(planes.values()))
    out = np.zeros((round(height * scale), round(SHEET_W * scale)) + first.shape[2:], np.float32)
    for c in cuts:
        x, y, w, h = (round(v * scale) for v in c["box"])
        sx, sy = (round(v * scale) for v in c["on"][:2])
        out[sy:sy + h, sx:sx + w] = planes[c["piece"]][y:y + h, x:x + w]
    return out


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
    group, extra = added(kv, group)
    whole = pieces(poster, kv, group, extra, 1)
    cuts = cutouts(whole["cover"])
    height = max(c["on"][1] + c["on"][3] for c in cuts)
    for old in OUT.glob("*.webp"):
        old.unlink()
    for i, (far, mid, near, width, quality) in enumerate(LENS):
        scale = width / W
        if i == 0:
            fit(poster, width).save(OUT / "0.webp", "WEBP", quality=quality, method=6)
            sharp = pieces(poster, kv, group, extra, scale)
            stage, lit, cover = laid(sharp, 0, scale)
        else:
            stage, lit, cover = laid(whole, i, 1)
            rest = Image.fromarray(as_bytes(together(stage, lit, cover)))
            fit(rest, width).save(OUT / f"{i}.webp", "WEBP", quality=quality, method=6)
            stage = sized(stage, width, round(width * H / W))
            lit = {k: sized(v, width, round(width * H / W)) for k, v in lit.items()}
            cover = {k: sized(v, width, round(width * H / W)) for k, v in cover.items()}
            scale = width / W
        Image.fromarray(as_bytes(stage)).save(OUT / f"stage-{i}.webp", "WEBP", quality=QUALITY, method=6)
        Image.fromarray(as_bytes(sheet(cuts, lit, scale, height))).save(
            OUT / f"layers-{i}.webp", "WEBP", quality=QUALITY, method=6)
        Image.fromarray((np.clip(sheet(cuts, cover, scale, height), 0, 1) * 255).round().astype(np.uint8)).convert("RGB").save(
            OUT / f"cover-{i}.webp", "WEBP", lossless=not i, quality=100 if not i else COVER_QUALITY, method=6)
    depth = sized(nearness(whole["part"]), W // 2, H // 2)
    Image.fromarray((np.clip(depth, 0, 1) * 255).round().astype(np.uint8)).save(OUT / "depth.webp", "WEBP", lossless=True,
                                                                                quality=100, method=6)
    layout = {
        "sheet": [SHEET_W / W, height / H],
        "cuts": [{"name": c["name"], "in": [c["box"][0] / W, c["box"][1] / H, c["box"][2] / W, c["box"][3] / H],
                  "on": [c["on"][0] / SHEET_W, c["on"][1] / height, c["on"][2] / SHEET_W, c["on"][3] / height],
                  "near": c["near"]}
                 for c in sorted(cuts, key=lambda c: [n for n, _, _ in LAYERS].index(c["piece"]))],
    }
    (OUT / "layout.json").write_text(json.dumps(layout, indent=1) + "\n")
    title = Image.open(WORK / "src/logo-title.png")
    title.save(OUT.parent / "title.webp", "WEBP", quality=90, alpha_quality=100, method=6)
    for f in [*sorted(OUT.glob("*.webp")), OUT / "layout.json", OUT.parent / "title.webp"]:
        print(f"{f.name:14} {f.stat().st_size:8}", Image.open(f).size if f.suffix == ".webp" else "")


if __name__ == "__main__":
    main()
