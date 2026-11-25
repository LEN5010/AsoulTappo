#!/usr/bin/env python3
"""Small pictures of the photocards, for the album, the shop and the spread of an opened box.

    python scripts/photocards/thumbs.py [series ...]

Reads <series>/front, <series>/sign and <series>/cards.json of client/src/assets/photocards/ and writes
  <series>/thumb/<card>.webp         the front, SHORT texels on its short side
  <series>/thumb/sign-<member>.webp  the signature alone at the same scale, transparent around it

pack.py runs this for the series it packs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parents[2] / "client/src/assets/photocards"
SHORT = 324
# The ink and the edge it darkens, as the opening's small pictures have them (THUMB_FS).
INK, EDGE = np.array([0.80, 0.60, 0.23]), np.array([0.20, 0.11, 0.03])


def small(src: Path, out: Path) -> None:
    image = Image.open(src).convert("RGB")
    k = SHORT / min(image.size)
    image.resize((round(image.width * k), round(image.height * k)), Image.LANCZOS).save(out, "WEBP", quality=84, method=6)


def signature(src: Path, out: Path, box: list[int], short: int) -> None:
    """R of the encoded signature is its coverage, B the distance to its edge: 0.5 on it, 1 a dozen texels outside."""
    k = SHORT / short
    size = (round(box[2] * k), round(box[3] * k))
    sign = np.asarray(Image.open(src).convert("RGB").resize(size, Image.LANCZOS), dtype=np.float64) / 255
    ink = sign[..., 0]
    edge = 0.40 * np.clip(1.2 - (sign[..., 2] - 0.5) * 24, 0, 1)
    alpha = 1 - (1 - edge) * (1 - ink)
    colour = (EDGE * (edge * (1 - ink))[..., None] + INK * ink[..., None]) / np.maximum(alpha, 1e-4)[..., None]
    rgba = np.dstack([np.clip(colour, 0, 1), alpha])
    Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(out, "WEBP", quality=88, method=6, alpha_quality=95)


def build(series: str) -> None:
    art = ASSETS / series
    out = art / "thumb"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.webp"):
        old.unlink()
    cards = json.loads((art / "cards.json").read_text())
    for front in sorted((art / "front").glob("*.webp")):
        small(front, out / front.name)
    for member, sign in cards["signs"].items():
        signature(art / "sign" / f"{member}.webp", out / f"sign-{member}.webp", sign["box"],
                  min(cards["templates"][member]["size"]))
    files = list(out.glob("*.webp"))
    print(f"{series}: {len(files)} small pictures, {sum(f.stat().st_size for f in files) / 1e3:.0f} KB")


if __name__ == "__main__":
    for name in sys.argv[1:] or sorted(d.name for d in ASSETS.iterdir() if (d / "cards.json").exists()):
        build(name)
