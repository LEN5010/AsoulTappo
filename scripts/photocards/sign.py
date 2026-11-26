#!/usr/bin/env python3
"""Build the signature textures: tex/sign-<member>.webp and tex/signs.json, from the three stroke animations in src/sign/.

    PLAYWRIGHT=<playwright-core directory> CHROMIUM=<headless Chromium> python scripts/photocards/sign.py

The three channels:
  R  the finished signature: the coverage of the animation's last frame, its lines made thicker
  G  when the pen first reaches a pixel, 0 to 255 over the whole time, spread outward from the ink
  B  the distance to the ink's edge: 255 is 12 px outside, 128 the edge, 0 is 12 px inside

Sources are not in git; PHOTOCARDS names the working directory (README.md).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ["PHOTOCARDS"])
# Where a signature lies on the card, in texels of the card (short side 1080). What goes past the card's edge is cut off.
# 嘉然's is registered stroke by stroke against a photo of a printed one (diana-3): k is texels per SVG unit, angle is degrees
# clockwise, at is where the SVG's origin falls, so a point on the card is k * rotate(SVG point) + at. Registered, at is
# [509.4, 772.8], and the right end goes 57 texels past the edge; it is moved 67 to the left so that none of it is cut off.
# The signature has another face since; the strokes it shares with the printed one lie where they did.
# There is no photo of 贝拉's and 乃琳's: they take the same area, the ink's right at 1136 and bottom at 1455, unturned.
PLACE = {
    "diana": {"k": 0.3829, "angle": 20.21, "at": [442.4, 772.8]},
    "bella": {"right": 1136, "bottom": 1455, "width": 820, "angle": 0},
    "eileen": {"right": 1136, "bottom": 1455, "width": 716, "angle": 0},
}
SS = 4          # supersampling
MARGIN = 14     # texels left around the ink
REACH = 12      # the range of B
TIPS = 120      # steps of the pen's path
SPEED = 0.34    # writing takes this much of the animation's time
# The pen is broader than the lines were: thin lines grow to a half-width of HALF, thick ones by LEAST only, none by more than
# MOST; gaps between strokes and the holes in letters keep a half-width of KEEP.
HALF, LEAST, MOST, KEEP = 5.2, 1.3, 3.0, 2.9


def numbers(d):
    return np.array([float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]).reshape(-1, 2)


class Art:
    """The pieces of the SVG: shape, the line the pen follows, its radius, when."""

    def __init__(self, svg):
        text = Path(svg).read_text(encoding="utf-8")
        self.box = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split()]
        self.ms = round(float(re.search(r'data-duration="([^"]+)"', text).group(1)) * 1000)
        clips = dict(re.findall(r'<clipPath id="(s\d+)"><path d="([^"]+)"', text))
        self.pieces = []
        pat = (r'<g clip-path="url\(#(s\d+)\)"><path d="([^"]+)" stroke-width="([\d.]+)" stroke-dasharray="([\d.]+) [\d.]+"'
               r'.*?<animate [^>]*begin="([\d.]+)s" dur="([\d.]+)s" values="([^"]+)" keyTimes="([^"]+)"')
        for sid, d, sw, total, t0, dur, vals, keys in re.findall(pat, text):
            self.pieces.append({
                "shape": [numbers(p) for p in re.findall(r"M[^MZ]+Z?", clips[sid])],
                "line": numbers(d), "r": float(sw) / 2, "t0": float(t0), "dur": float(dur),
                "drawn": float(total) - np.array([float(v) for v in vals.split(";")]),
                "keys": np.array([float(v) for v in keys.split(";")]),
            })
        if len(self.pieces) != text.count("<animate "):
            raise SystemExit(f"{svg}: {len(self.pieces)} pieces read of {text.count('<animate ')}")

    def tips(self, k):
        """Where the pen goes: time in seconds and place, k px per SVG unit, in order of time."""
        rows = []
        for p in self.pieces:
            line = (p["line"] - self.box[:2]) * k
            at = np.r_[0, np.cumsum(np.hypot(*np.diff(line, axis=0).T))] / k
            s = np.linspace(0, at[-1], max(2, int(at[-1] * k / 2)))
            s = s[s <= p["drawn"][-1] + 1e-6]
            q = np.stack([np.interp(s, at, line[:, i]) for i in (0, 1)], 1)
            rows.append(np.c_[p["t0"] + np.interp(s, p["drawn"], p["keys"], left=0, right=1) * p["dur"], q])
        rows = np.concatenate(rows)
        return rows[np.argsort(rows[:, 0], kind="stable")]

    def times(self, k, size):
        """When the pen first reaches each pixel, in seconds, infinite where there is no ink; k px per SVG unit."""
        w, h = size
        out = np.full((h, w), np.inf, np.float32)
        x, y = self.box[:2]
        for p in self.pieces:
            mask = np.zeros((h, w), np.uint8)
            cv2.fillPoly(mask, [np.round((s - [x, y]) * k * 16).astype(np.int32) for s in p["shape"] if len(s) > 2], 255, shift=4)
            line, r = (p["line"] - [x, y]) * k, p["r"] * k
            at = np.r_[0, np.cumsum(np.hypot(*np.diff(line, axis=0).T))] / k
            s = np.linspace(0, at[-1], max(2, int(at[-1] * k / 1.5)))
            s = s[s <= p["drawn"][-1] + 1e-6]
            q = np.stack([np.interp(s, at, line[:, i]) for i in (0, 1)], 1)
            t = p["t0"] + np.interp(s, p["drawn"], p["keys"], left=0, right=1) * p["dur"]
            x0, x1 = max(0, int(line[:, 0].min() - r - 2)), min(w, int(line[:, 0].max() + r + 3))
            y0, y1 = max(0, int(line[:, 1].min() - r - 2)), min(h, int(line[:, 1].max() + r + 3))
            here = np.full((y1 - y0, x1 - x0), np.inf, np.float32)
            # Drawn backwards, so what comes early covers what comes late.
            for (cx, cy), ti in list(zip(q, t))[::-1]:
                cv2.circle(here, (int(round((cx - x0) * 16)), int(round((cy - y0) * 16))), int(round(r * 16)), float(ti), -1, shift=4)
            ok = (mask[y0:y1, x0:x1] > 127) & np.isfinite(here)
            part = out[y0:y1, x0:x1]
            part[ok] = np.minimum(part[ok], here[ok])
        return out


def spread(value, known):
    """The values at `known`, carried to the nearest other pixels."""
    _, label = cv2.distanceTransformWithLabels((~known).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    table = np.zeros(label.max() + 1, value.dtype)
    table[label[known]] = value[known]
    return table[label]


def pool(a, n):
    """The largest of each n by n block."""
    h, w = a.shape
    return a.reshape(h // n, n, w // n, n).max((1, 3))


def thicken(pad):
    """Makes the lines thicker."""
    ink = pad >= 128
    inner = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5) / SS
    outer = cv2.distanceTransform((~ink).astype(np.uint8), cv2.DIST_L2, 5) / SS
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    solid = pool(ink.astype(np.uint8), SS) > 0
    width = cv2.dilate(pool(inner, SS).astype(np.float32), disc)          # half-width of the strokes near here
    width = spread(np.where(solid, width, 0).astype(np.float32), solid)
    gap = cv2.dilate(pool(outer, SS).astype(np.float32), disc)            # half-width of the gaps near here
    width = cv2.GaussianBlur(width, (0, 0), 5)
    grow = np.minimum(np.clip(HALF - width, LEAST, MOST), np.clip(gap - KEEP, 0.25, None)).astype(np.float32)
    grow = cv2.GaussianBlur(grow, (0, 0), 3)
    grow = cv2.resize(grow, (pad.shape[1], pad.shape[0]), interpolation=cv2.INTER_LINEAR)
    fat = np.where(outer <= grow, 255, 0).astype(np.uint8)
    fat = np.where(cv2.GaussianBlur(fat, (0, 0), SS * 1.0) >= 128, 255, 0).astype(np.uint8)
    # Holes in small letters stay as they were.
    tight = cv2.resize(cv2.GaussianBlur((gap < 2.6).astype(np.float32), (0, 0), 1), (pad.shape[1], pad.shape[0]), interpolation=cv2.INTER_LINEAR) > 0.35
    hole = ~ink & tight & (fat > 0)
    fat[hole] = 0
    return fat


def build(who):
    art = Art(ROOT / f"src/sign/{who}.svg")
    place = PLACE[who]
    angle = place["angle"]
    bw, bh = art.box[2:]
    c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    if "k" in place:
        k = place["k"]
    else:
        rough = np.isfinite(art.times(1, (int(np.ceil(bw)), int(np.ceil(bh)))))
        ry, rx = np.nonzero(rough)
        across = rx * c - ry * s
        k = place["width"] / (across.max() - across.min() + 1)
    size = (int(np.ceil(bw * k * SS)), int(np.ceil(bh * k * SS)))
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "end.png")
        subprocess.run(["node", str(HERE / "sign.cjs"), str(ROOT / f"src/sign/{who}.svg"), png, str(bw * k * SS), str(bh * k * SS)], check=True)
        ink = 255 - cv2.imread(png, 0)
    ink = ink[:size[1], :size[0]]
    seen = art.times(k * SS, (ink.shape[1], ink.shape[0]))
    turn = np.float64([[1, 0, 0], [0, 1, 0]])
    ox0 = oy0 = 0.0
    if angle:
        h0, w0 = ink.shape
        ends = np.float64([[0, 0], [w0, 0], [0, h0], [w0, h0]]) @ np.float64([[c, s], [-s, c]])
        ox0, oy0 = ends.min(0)
        size = tuple(int(np.ceil(v)) for v in ends.max(0) - ends.min(0))
        turn = np.float64([[c, -s, -ox0], [s, c, -oy0]])
        ink = cv2.warpAffine(ink, turn, size, flags=cv2.INTER_LINEAR)
        seen = cv2.warpAffine(np.where(np.isfinite(seen), seen, 1e9).astype(np.float32), turn, size, flags=cv2.INTER_NEAREST, borderValue=1e9)
        seen = np.where(seen < 1e8, seen, np.inf).astype(np.float32)
    ys, xs = np.nonzero(ink > 8)
    # A point X of the supersampled canvas falls on the card at X / SS + corner.
    vx, vy = art.box[:2]
    if "at" in place:
        corner = np.float64([ox0 / SS + k * (c * vx - s * vy) + place["at"][0], oy0 / SS + k * (s * vx + c * vy) + place["at"][1]])
    else:
        corner = np.float64([place["right"] - (xs.max() + 1) / SS, place["bottom"] - (ys.max() + 1) / SS])
    # The ink's box falls on whole texels of the card, with a margin.
    x0, y0 = int(np.floor(xs.min() / SS + corner[0])) - MARGIN, int(np.floor(ys.min() / SS + corner[1])) - MARGIN
    w = int(np.ceil((xs.max() + 1) / SS + corner[0])) + MARGIN - x0
    h = int(np.ceil((ys.max() + 1) / SS + corner[1])) + MARGIN - y0
    pad = np.zeros((h * SS, w * SS), np.uint8)
    time4 = np.full(pad.shape, np.inf, np.float32)
    ox, oy = int(round((x0 - corner[0]) * SS)), int(round((y0 - corner[1]) * SS))
    sx0, sy0 = max(0, ox), max(0, oy)
    sx1, sy1 = min(ink.shape[1], ox + w * SS), min(ink.shape[0], oy + h * SS)
    pad[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox] = ink[sy0:sy1, sx0:sx1]
    time4[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox] = seen[sy0:sy1, sx0:sx1]
    known4 = np.isfinite(time4)
    thin = (pad >= 128).sum()
    pad = thicken(pad)
    fat = (pad >= 128).sum() / thin
    lost = int((pad > 60).sum() - (pad[MARGIN * SS // 2:-MARGIN * SS // 2, MARGIN * SS // 2:-MARGIN * SS // 2] > 60).sum())
    cover = cv2.resize(pad, (w, h), interpolation=cv2.INTER_AREA)
    time4 = np.where(known4, time4, 1e9)
    first = time4.reshape(h, SS, w, SS).min((1, 3))          # the earliest within a texel
    known = first < 1e8
    first = spread(np.where(known, first, 0).astype(np.float32), known)
    far = cv2.distanceTransform((pad < 128).astype(np.uint8), cv2.DIST_L2, 5) - cv2.distanceTransform((pad >= 128).astype(np.uint8), cv2.DIST_L2, 5)
    far = cv2.resize(far / SS, (w, h), interpolation=cv2.INTER_AREA)
    tex = np.dstack([cover, np.round(np.clip(first * 1000 / art.ms, 0, 1) * 255), np.round(np.clip(0.5 + far / (2 * REACH), 0, 1) * 255)]).astype(np.uint8)
    path = ROOT / f"tex/sign-{who}.webp"
    Image.fromarray(tex).save(path, "WEBP", lossless=True, quality=100, method=6, exact=True)
    box = [x0, y0, w, h]
    # The pen's path in texels of the card, sampled evenly; null while the pen is up.
    tip, rows = [], art.tips(k * SS)
    rows[:, 1:] = rows[:, 1:] @ turn[:, :2].T + turn[:, 2]
    rows = rows[rows[:, 0] <= art.ms / 1000]
    for i in range(TIPS + 1):
        n = np.searchsorted(rows[:, 0], i / TIPS * art.ms / 1000, side="right") - 1
        late = n < 0 or i / TIPS * art.ms / 1000 - rows[n, 0] > 0.09
        tip.append(None if late else [round((rows[n, 1] - ox) / SS + box[0]), round((rows[n, 2] - oy) / SS + box[1])])
    no_time = ((cover > 25) & ~known)
    print(f"{who}: {k:.4f} px per unit, {w}x{h} at {box}, {art.ms} ms (written in {round(art.ms * SPEED)}), {fat:.2f} times the ink, "
          f"{path.stat().st_size / 1024:.1f} KB, ink at the border {lost}, ink without a time {int(no_time.sum())}")
    return {"box": box, "ms": round(art.ms * SPEED), "tip": tip}


signs = {who: build(who) for who in PLACE}
(ROOT / "tex/signs.json").write_text(json.dumps({"built": int(time.time()), "signs": signs}) + "\n")
