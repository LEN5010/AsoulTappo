#!/usr/bin/env python3
"""Turn the built photocard textures into the client's assets.

    PHOTOCARDS=<working directory> python scripts/photocards/pack.py

Reads tex/ and open/tex/ of the working directory (README.md) and writes client/src/assets/photocards/:
  <series>/front/<card>.webp   what is printed on the front, as build_tex.py wrote it
  <series>/back/<back>.webp    the backs: one for each member, one for every sideways card
  <series>/mat/<front|back>-<template>.webp   the finishes, lossless; cards of one template share theirs
  <series>/sign/<member>.webp  the signatures, as sign.py wrote them
  <series>/box.webp            what is printed on the box, lossless
  <series>/cards.json          the look of the series (the colours of the box's board, of its rubbed folds, of the light
                               behind it on the page, and of the key visual's stage), the templates (size, back, colours of the foil and the
                               print), who stands where in the sideways pictures, and where each signature lies, how
                               long it takes to write, and the pen's path
  <series>/thumb/*.webp        the small pictures (thumbs.py)
  open/*.webp                  what every opening shares, lossless
The pictures of the box on the page (<series>/shop/, poster.cjs) and the key visual (<series>/stage/ and title.webp,
stage.py) are kept.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import thumbs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "client/src/assets/photocards"
SERIES = "asoul2026"
LOOK = {
    "box": [0.575, 0.430, 0.775], "rub": [0.78, 0.71, 0.86], "wash": "#9670cd",
    # The key visual: what it is shaded with, the light it whitens through into the page's paper, the ground under it from
    # top to bottom, the colour of its lamps and where they are.
    "stage": {"dark": [0.082, 0.051, 0.180], "mist": [0.80, 0.63, 0.98],
              "ground": [[0.090, 0.063, 0.196], [0.035, 0.020, 0.086]],
              "light": [0.80, 0.72, 1.0], "lamps": [[0.253, 0.106], [0.3375, 0.139], [0.616, 0.069]]},
}
# Left to right in the picture; the names under a duo are not always in this order.
STAND = {
    "diana-eileen-1": ["eileen", "diana"], "diana-eileen-2": ["diana", "eileen"],
    "bella-eileen-1": ["bella", "eileen"], "bella-eileen-2": ["bella", "eileen"],
    "bella-diana-1": ["diana", "bella"], "bella-diana-2": ["bella", "diana"],
    "group-1": ["diana", "eileen", "bella"], "group-2": ["eileen", "diana", "bella"],
    "group-3": ["eileen", "diana", "bella"], "group-4": ["eileen", "bella", "diana"],
}


def template_of(card: str) -> str:
    """Cards that differ only in their picture: their id without its number."""
    return re.sub(r"-\d+$", "", card)


def lossless(src: Path, out: Path) -> None:
    image = Image.open(src)
    image.save(out, "WEBP", lossless=True, quality=100, method=6, exact=True)
    if not np.array_equal(np.asarray(Image.open(out).convert("RGB")), np.asarray(image.convert("RGB"))):
        raise SystemExit(f"{out} is not {src}")


def same(files: list[Path]) -> Path:
    """The first of `files`, which have to be the same picture."""
    first = np.asarray(Image.open(files[0]))
    for f in files[1:]:
        if not np.array_equal(first, np.asarray(Image.open(f))):
            raise SystemExit(f"{f.name} differs from {files[0].name}")
    return files[0]


def main() -> None:
    work = Path(os.environ["PHOTOCARDS"])
    tex, out = work / "tex", OUT / SERIES
    cards = json.loads((tex / "cards.json").read_text())["cards"]
    signs = json.loads((tex / "signs.json").read_text())["signs"]
    for d in ("front", "back", "mat", "sign"):
        shutil.rmtree(out / d, ignore_errors=True)
        (out / d).mkdir(parents=True)
    shutil.rmtree(OUT / "open", ignore_errors=True)
    (OUT / "open").mkdir()

    templates: dict[str, dict] = {}
    for card in cards:
        shutil.copyfile(tex / f"{card['id']}-front-base.webp", out / "front" / f"{card['id']}.webp")
        mine = {k: card[k] for k in ("size", "back", "foil", "print")}
        if templates.setdefault(template_of(card["id"]), mine) != mine:
            raise SystemExit(f"{card['id']} differs from the others of its template")
    if missing := {c["id"] for c in cards if c["size"][0] > c["size"][1]} ^ STAND.keys():
        raise SystemExit(f"who stands where: {sorted(missing)}")
    for t in templates:
        files = [tex / f"{c['id']}-front-mat.png" for c in cards if template_of(c["id"]) == t]
        lossless(same(files), out / "mat" / f"front-{t}.webp")
    for back in sorted({t["back"] for t in templates.values()}):
        shutil.copyfile(tex / f"{back}-back-base.webp", out / "back" / f"{back}.webp")
        lossless(tex / f"{back}-back-mat.png", out / "mat" / f"back-{back}.webp")
    for member in signs:
        shutil.copyfile(tex / f"sign-{member}.webp", out / "sign" / f"{member}.webp")
    for name in ("room", "shadow"):
        lossless(work / "open/tex" / f"{name}.png", OUT / "open" / f"{name}.webp")
    lossless(work / "open/tex/box-print.png", out / "box.webp")

    def rows(d: dict) -> str:
        return "{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in d.items()) + "\n }"
    (out / "cards.json").write_text(
        f'{{\n "look": {json.dumps(LOOK)},\n "templates": {rows(templates)},\n "stand": {rows(STAND)},\n'
        f' "signs": {rows(signs)}\n}}\n')
    thumbs.build(SERIES)
    files = [f for f in OUT.rglob("*") if f.is_file()]
    print(f"{len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.2f} MB")


if __name__ == "__main__":
    sys.exit(main())
