#!/usr/bin/env python3
"""Bake the key visual of a series into the pictures its page stands on.

    PHOTOCARDS=<working directory> python scripts/photocards/stage.py

Reads src/kv/ of the working directory: clean/poster.jpg is the key visual without its lettering, mask.png the members
and what stands with them, white on black at any size of the same shape (lift.swift cuts it on a Mac). Writes
client/src/assets/photocards/<series>/stage/:
  0.webp to 4.webp   the key visual from sharp, the members in focus, to the blur it has behind the box: the farther
                     from the lens' distance, the wider each thing is spread, so the page pulls focus by crossing over
                     from one to the next
  depth.webp         how near everything is, white the nearest, by which it moves as the page is looked at from aside
and the event's title as title.webp beside it, from src/logo-title.png (logo.py).
"""
from __future__ import annotations

import os
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
#: How near things are, at points of the group: x, y, 0 to 1.
NEAR = [
    (245, 215, .52), (285, 360, .55), (280, 520, .57), (250, 720, .56), (330, 860, .56), (500, 300, .42), (560, 420, .40),
    (470, 470, .44), (110, 520, .50), (60, 600, .50), (95, 330, .60), (370, 480, .60), (110, 330, .36), (40, 420, .36),
    (685, 220, .44), (710, 400, .47), (720, 560, .48), (750, 740, .47), (865, 295, .52), (900, 430, .40), (560, 540, .43),
    (480, 600, .42), (1000, 470, .40), (1200, 180, .78), (1080, 110, .86), (1060, 190, .84), (905, 320, .82), (1000, 340, .78),
    (1260, 430, .76), (1260, 560, .76), (1230, 740, .82), (1120, 860, .84), (1330, 230, .84), (1420, 330, .80), (900, 640, .68),
    (960, 520, .70), (870, 770, .70), (1480, 480, .62), (1500, 230, .60), (1440, 700, .66), (520, 700, .26), (640, 780, .28),
    (440, 760, .30), (560, 860, .28),
]


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
    pic = linear(np.asarray(poster.resize((W, H), Image.LANCZOS)).astype(np.float32) / 255)
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

    # How near: the stage, a little nearer toward its floor and at its pillars; the group between its points; the front.
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    stage = .03 + .13 * np.clip((y - 300) / 600, 0, 1)
    for x0, x1, v in [(775, 882, .20), (1366, 1422, .22)]:
        stage = np.maximum(stage, v * np.clip((x - x0) / 8, 0, 1) * np.clip((x1 - x) / 8, 0, 1))
    total, sum_ = np.zeros((H, W), np.float32), np.zeros((H, W), np.float32)
    for px, py, v in NEAR:
        k = 1 / (np.hypot(x - px, y - py) + 12) ** 3.2
        total += k
        sum_ += k * v
    # The edge of the group lies outside it, so what gives way as it moves is the stage.
    wide = cv2.GaussianBlur(cv2.dilate(group, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))), (0, 0), 7)
    depth = stage * (1 - wide) + sum_ / total * wide
    fwide = cv2.GaussianBlur(cv2.dilate(front, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (23, 23))), (0, 0), 7)
    depth = depth * (1 - fwide) + fwide
    depth = cv2.GaussianBlur(depth, (0, 0), 3)
    small = Image.fromarray((np.clip(depth, 0, 1) * 255).round().astype(np.uint8)).resize((480, 270), Image.LANCZOS)
    small.save(OUT / "depth.webp", "WEBP", quality=90, method=6)
    title = Image.open(WORK / "src/logo-title.png")
    title.save(OUT.parent / "title.webp", "WEBP", quality=90, alpha_quality=100, method=6)
    for f in [*sorted(OUT.glob("*.webp")), OUT.parent / "title.webp"]:
        print(f"{f.name:12} {f.stat().st_size:8} {Image.open(f).size}")


if __name__ == "__main__":
    main()
