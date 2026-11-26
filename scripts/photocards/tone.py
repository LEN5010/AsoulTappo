#!/usr/bin/env python3
"""What a scan of the photocards has to be corrected by, measured against the event's sale poster.

    PHOTOCARDS=<working directory> python scripts/photocards/tone.py

A scanner without a colour profile greys a card: its paper is not white, its lights are dim, its colours are dull.
The sale poster shows the design of every card, a sixth as large as a texture. Once a scan's paper is made white its
hues are those of the design, all but the blues, which are printed violet (photos of the cards show them so too). This
writes tone.json, for build_tex.py:
  gain   what the chroma of a scan is multiplied by, for every 30 degrees of hue from 0; never less than 1
  white  for every card, what takes what is white in its picture to the design's white, once the paper is white (as light)
  light  for every card, the line its lightness is taken along after that: offset and slope (OKLab, 0 to 1)
  frame  the colours of a frame from top to bottom, at the steps of its ramp, by the name of the cards' back: the scan's
         at the dark end, and from there the way they go on the design. Further down a scan shows the pearl of the
         cross-hatching more than the ink, grey or yellow.
The hues stay those of the print.
"""
from __future__ import annotations

import json
import sys

import cv2
import numpy as np

import build_tex
from build_tex import balanced, decoded, oklab, paper, toned

# Where each card is on the poster: left, top, width, height in its pixels, found by matching the built fronts with it.
POSTER = "poster/sale-details.jpg"
PLACES = {
    "bella-1": (157.56, 2558.37, 160.8, 253.2), "bella-2": (760.63, 2557.57, 161.1, 254.7),
    "bella-3": (559.64, 2557.57, 161.0, 254.5), "bella-4": (358.85, 2557.47, 160.7, 254.9),
    "diana-1": (157.96, 2839.46, 160.5, 254.7), "diana-2": (358.85, 2839.56, 160.7, 254.6),
    "diana-3": (760.83, 2839.56, 160.7, 254.6), "diana-4": (559.84, 2839.86, 160.7, 254.1),
    "eileen-1": (157.66, 3121.66, 160.9, 254.5), "eileen-2": (358.75, 3121.66, 160.8, 254.4),
    "eileen-3": (559.94, 3121.76, 160.6, 254.3), "eileen-4": (760.63, 3121.96, 160.9, 254.0),
    "bella-diana-1": (128.67, 3510.18, 255.9, 161.6), "bella-diana-2": (128.37, 3684.92, 256.3, 161.9),
    "bella-eileen-1": (696.5, 3684.82, 256.6, 162.0), "bella-eileen-2": (696.5, 3509.78, 256.2, 162.0),
    "diana-eileen-1": (413.5, 3684.82, 256.2, 162.0), "diana-eileen-2": (413.5, 3510.18, 256.6, 161.7),
    "group-1": (129.38, 3972.67, 256.7, 162.3), "group-2": (414.61, 3972.77, 256.4, 162.1),
    "group-3": (414.5, 4147.7, 256.8, 162.3), "group-4": (697.51, 3972.57, 256.6, 162.4),
}
WHITE = 254 / 255      # the poster's white
KNOTS = 12
MOST = 1.3


def read(name):
    return cv2.cvtColor(cv2.imread(str(build_tex.SOURCES / name)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255


def design(poster, card):
    """A card as the poster shows it, as large as it is there."""
    x, y, w, h = PLACES[card]
    nx, ny = (256, 162) if w > h else (161, 254)
    place = np.float32([[w / nx, 0, x - 0.5 + 0.5 * w / nx], [0, h / ny, y - 0.5 + 0.5 * h / ny]])
    return cv2.warpAffine(poster, place, (nx, ny), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)


def pairs(spec, want):
    """The flat parts of a card's picture on its scan, its paper made white, and on its design, as light."""
    h, w = want.shape[:2]
    have = cv2.resize(read(spec["source"]), (w, h), interpolation=cv2.INTER_AREA)
    k = w / spec["size"][0]
    x0, y0, x1, y1 = (round(v * k) + d for v, d in zip(spec["window"], (3, 3, -3, -3)))
    use = np.zeros((h, w), bool)
    use[y0:y1, x0:x1] = True
    for bx0, by0, bx1, by1 in [spec["bar"]["box"]] + [p["box"] for p in spec["pills"]]:
        use[max(0, int(by0 * k) - 3):int(by1 * k) + 4, max(0, int(bx0 * k) - 3):int(bx1 * k) + 4] = False
    have, want = (cv2.GaussianBlur(a, (0, 0), 1.3).astype(np.float64) for a in (have, want))
    grey = have.mean(axis=2)
    steep = np.hypot(cv2.Sobel(grey, cv2.CV_64F, 1, 0), cv2.Sobel(grey, cv2.CV_64F, 0, 1))
    use &= steep < np.percentile(steep[use], 70)
    return decoded(have[use]) / decoded(paper(spec)), decoded(want[use]) / decoded(WHITE)


def balance(have, want):
    """What takes the scan's whites to the design's, without making them lighter. 1 for a picture with next to none."""
    lab = oklab(want)
    white = (lab[:, 0] > 0.8) & (np.hypot(lab[:, 1], lab[:, 2]) < 0.03)
    if white.sum() < 80:
        return np.ones(3)
    g = np.median(want[white] / np.maximum(have[white], 1e-4), axis=0)
    return g / (g @ [0.2126, 0.7152, 0.0722])


def line(x, y):
    """Offset and slope of y over x, what lies off the line counting less."""
    a, weight = np.c_[np.ones(len(x)), x], np.ones(len(x))
    for _ in range(8):
        aw = a * weight[:, None]
        m = np.linalg.solve(aw.T @ a, aw.T @ y)
        off = np.abs(a @ m - y)
        weight = 1 / np.maximum(1, off / (1.5 * 1.4826 * np.median(off) + 1e-6))
    return m


def gains(have, want):
    """By hue, how much fuller the design is than the scan, from what has a colour at all; where nothing has, 1."""
    c, d = np.hypot(have[:, 1], have[:, 2]), np.hypot(want[:, 1], want[:, 2])
    use = c > 0.02
    c, d = c[use], d[use]
    at = (np.arctan2(have[use, 2], have[use, 1]) / (2 * np.pi) % 1) * KNOTS
    near = np.maximum(0, 1 - np.abs((at[:, None] - np.arange(KNOTS) + KNOTS / 2) % KNOTS - KNOTS / 2))
    few = 1e-3 * (c * c).sum() / KNOTS
    return np.clip((near.T @ (c * d) + few) / (near.T @ (c * c) + few), 1, MOST)


def frame(spec, designs):
    """The frame's colours from top to bottom, as hex."""
    (w, h), (step, stops) = spec["size"], spec["ramp"]
    k = designs[0].shape[1] / w
    x0, x1 = spec["window"][0] * k, spec["window"][2] * k
    # Between the picture and the columns the sparkles and the crosses stand in.
    strips = [d[:, s] for d in designs for s in (slice(round(x0 - 4.5), round(x0 - 2)), slice(round(x1 + 2.5), round(x1 + 4.5)))]
    rows = np.median(np.concatenate(strips, axis=1), axis=1)
    # A card's own edge is mixed with what it lies on.
    rows[:3], rows[-4:] = rows[3], rows[-5]
    soft = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    rows = np.stack([np.convolve(np.pad(c, 6, mode="edge"), soft / soft.sum(), mode="valid") for c in rows.T], axis=1)
    at = np.arange(len(stops)) * step * len(rows) / h
    # It only ever gets lighter: what dips again is the JPEG's noise.
    want = np.maximum.accumulate(np.stack([np.interp(at, np.arange(len(rows)) + 0.5, c) for c in rows.T], axis=1), axis=0)
    top = toned(np.float32([int(stops[0][i:i + 2], 16) for i in (0, 2, 4)]), spec) / 255
    cols = WHITE - (want[-1] - want) / (want[-1] - want[0]) * (WHITE - top)
    return ["%02X%02X%02X" % tuple(round(float(v) * 255) for v in c) for c in cols]


def main() -> None:
    specs, poster = build_tex.load_specs(), read(POSTER)
    designs = {card: design(poster, card) for card in PLACES}
    white, both = {}, {}
    for card, d in designs.items():
        have, want = pairs(specs[card], d)
        white[card] = balance(have, want).round(3).tolist()
        both[card] = oklab(balanced(have, white[card])), oklab(want)
    tone = {"gain": gains(*(np.concatenate(side) for side in zip(*both.values()))).round(3).tolist(), "white": white,
            "light": {card: line(h[:, 0], w[:, 0]).round(3).tolist() for card, (h, w) in both.items()}}
    frames: dict[str, list[str]] = {}
    for card in PLACES:
        frames.setdefault(specs[card]["back"]["name"], []).append(card)
    build_tex.TONE.update(tone)
    tone["frame"] = {name: frame(specs[cards[0]], [designs[c] for c in cards]) for name, cards in frames.items()}

    def rows(d: dict) -> str:
        return "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in d.items()) + "\n }"
    text = f'{{\n "gain": {json.dumps(tone["gain"])},\n "white": {rows(white)},\n "light": {rows(tone["light"])},\n "frame": {rows(tone["frame"])}\n}}\n'
    build_tex.TONE_FILE.write_text(text)
    print(text)


if __name__ == "__main__":
    sys.exit(main())
