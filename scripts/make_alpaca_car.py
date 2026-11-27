"""The alpaca's car on the race board (client/src/panel/park/RaceTrack.vue): the 阿草和TA的朋友们 sticker 兜风 without
the HHHH over it, cropped to the car and its two alpacas.

The lettering is a shape of its own in the sticker's alpha, apart from the car, so keeping only the largest shape
removes it cleanly. Outputs client/src/assets/park/alpaca-car.webp (WebP quality 85) and prints where the wheels'
hubs are, as shares of the picture, for RaceTrack's spokes.

    python scripts/make_alpaca_car.py "<AI高清>/[阿草和TA的朋友们_兜风]-0_sticker_static.png"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "client/src/assets/park/alpaca-car.webp"
WIDTH = 400
SOLID = 16


def largest_shape(im: Image.Image) -> Image.Image:
    """[im] with every pixel outside its largest shape of alpha over SOLID (8-connected) made transparent."""
    w, h = im.size
    alpha = im.getchannel("A").load()
    seen = bytearray(w * h)
    best: list[int] = []
    for start in range(w * h):
        if seen[start] or alpha[start % w, start // w] <= SOLID:
            continue
        seen[start] = 1
        stack, shape = [start], []
        while stack:
            p = stack.pop()
            shape.append(p)
            x, y = p % w, p // w
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        q = ny * w + nx
                        if not seen[q] and alpha[nx, ny] > SOLID:
                            seen[q] = 1
                            stack.append(q)
        if len(shape) > len(best):
            best = shape
    keep = Image.new("L", (w, h), 0)
    kp = keep.load()
    for p in best:
        kp[p % w, p // w] = 255
    out = im.copy()
    out.putalpha(Image.composite(im.getchannel("A"), Image.new("L", (w, h), 0), keep.point(lambda v: 255 if v else 0)))
    return out


def hubs(im: Image.Image) -> list[tuple[float, float, float]]:
    """The wheels' hub discs (light grey, in the lower half): each one's centre and radius in pixels."""
    w, h = im.size
    px = im.load()
    found: list[tuple[float, float, float]] = []
    seen: set[tuple[int, int]] = set()
    for y in range(h // 2, h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if (x, y) in seen or a < 200 or abs(r - g) > 12 or abs(g - b) > 12 or not 150 < r < 225:
                continue
            stack, shape = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                shape.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and h // 2 <= ny < h and (nx, ny) not in seen:
                        q = px[nx, ny]
                        if q[3] >= 200 and abs(q[0] - q[1]) <= 12 and abs(q[1] - q[2]) <= 12 and 150 < q[0] < 225:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            if len(shape) > 0.002 * w * h:
                xs = [p[0] for p in shape]
                ys = [p[1] for p in shape]
                found.append(((min(xs) + max(xs) + 1) / 2, (min(ys) + max(ys) + 1) / 2, (max(xs) - min(xs) + 1) / 2))
    return sorted(found)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", type=Path, help="the sticker 兜风 (AI高清, 648 px)")
    args = ap.parse_args()
    im = largest_shape(Image.open(args.source).convert("RGBA"))
    im = im.crop(im.getchannel("A").point(lambda v: 255 if v > SOLID else 0).getbbox())
    out = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.save(OUT, "WEBP", quality=85, method=6)
    print(f"{OUT.relative_to(ROOT)}: {out.width}x{out.height}, {OUT.stat().st_size} bytes")
    for x, y, r in hubs(im):
        print(f"hub at {x / im.width:.4f}, {y / im.height:.4f} of the picture, radius {r / im.width:.4f} of its width")


if __name__ == "__main__":
    main()
