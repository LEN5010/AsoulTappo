#!/usr/bin/env python3
"""Render the park coin (驼币) and the three stamp badges from the smiling 阿草 of the panel sidebar.

The 阿草 line art becomes an embossed relief on a reeded coin, lit from the upper left,
and is coloured with the UI's three gold tones (see docs/design/amusement-park.md §2.3).
Copper and silver badges reuse the same shading with their own three-tone ramps.

Run after changing the source picture or the colour tokens:
    server/.venv/bin/python scripts/make_coin.py [--preview PATH]

Outputs client/src/assets/park/coin.webp (256px), coin-64.webp and badge-{1,2,3}.webp (64px).
With --preview, also writes a contact sheet on light and dark backgrounds.
Pillow only; the output is deterministic.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageMath

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "client/src/assets/brand/side-alpaca.webp"
OUT = ROOT / "client/src/assets/park"
DEFAULT_PREVIEW = Path("/Users/len5010/code/AsoulTappo/docs/design/assets/coin-preview.png")

# Tokens from client/src/ui/tokens.css.
GOLD_SOFT = "#FFE3A6"
GOLD = "#E59B35"
C_700 = "#C34637"
C_800 = "#A12F35"
C_900 = "#652330"
PAPER = "#FFF7F2"  # --c-50, the page background
INK = "#3A222B"  # --ink

# Coin geometry, in units of the coin radius.
RIM_IN = 0.84  # rim is 8% of the diameter wide
LINE_R = 0.80  # thin raised line just inside the rim
REEDS = 120
# The source is a half-length figure cut flat at the bottom: head, bow tie and folded arms sit on
# the face, and the body runs on under the rim, fading out just inside it.
FIG_W = 1.2  # source width in coin radii
FIG_CX = 225  # source x placed on the vertical centre line (balances the two ears)
FIG_TOP = -0.60  # top of the source, in radii from the centre (negative is up); both ears stay inside FADE_R
FADE_R = (0.76, 0.83)  # the relief sinks into the field between these radii


# ---------------------------------------------------------------- colour


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c: float) -> float:
    c = max(0.0, min(1.0, c))
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return c * 255


def to_oklab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_lin(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def from_oklab(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )
    return tuple(round(_gam(c)) for c in rgb)  # type: ignore[return-value]


def mix(a: str | tuple, b: str | tuple, wa: float) -> tuple[int, int, int]:
    """CSS color-mix(in oklab, a wa, b)."""
    la = to_oklab(hex_rgb(a) if isinstance(a, str) else a)
    lb = to_oklab(hex_rgb(b) if isinstance(b, str) else b)
    return from_oklab(tuple(wa * x + (1 - wa) * y for x, y in zip(la, lb)))  # type: ignore[arg-type]


# Three tones per metal: light, mid, dark. Gold is the UI's own; copper and silver follow it,
# with the dark tone leaning into the coral ramp so shadows stay rose, never grey-brown.
PALETTES = {
    "gold": (hex_rgb(GOLD_SOFT), hex_rgb(GOLD), mix(GOLD, C_700, 0.4)),
    "copper": (hex_rgb("#FFD3B6"), hex_rgb("#CF7444"), mix("#CF7444", C_800, 0.35)),
    "silver": (hex_rgb("#FBF8F6"), hex_rgb("#B9B1AF"), mix("#B9B1AF", C_900, 0.45)),
}


def ramp_lut(pal: tuple[tuple[int, int, int], ...]) -> list[int]:
    """256-entry RGB lookup from tone 0..1, interpolated in OKLab.

    Only the three tones of the metal: dark holds through the deepest recesses, and the brightest
    glints lift light toward white the way frame-gold does (gold-soft mixed with #fff).
    """
    light, mid, dark = pal
    stops = [
        (0.00, dark),
        (0.22, dark),
        (0.50, mid),
        (0.84, light),
        (1.00, mix(light, "#FFFFFF", 0.55)),
    ]
    labs = [(t, to_oklab(c)) for t, c in stops]
    out: list[list[int]] = [[], [], []]
    for i in range(256):
        t = i / 255
        for (t0, c0), (t1, c1) in zip(labs, labs[1:]):
            if t <= t1:
                k = (t - t0) / (t1 - t0)
                rgb = from_oklab(tuple(x + (y - x) * k for x, y in zip(c0, c1)))  # type: ignore[arg-type]
                break
        for ch in range(3):
            out[ch].append(rgb[ch])
    return out[0] + out[1] + out[2]


# ---------------------------------------------------------------- float image helpers


def fmath(fn, **imgs) -> Image.Image:
    return ImageMath.lambda_eval(lambda a: fn(a), **imgs)


def shift(im: Image.Image, dx: int, dy: int) -> Image.Image:
    return ImageChops.offset(im, dx, dy)


def box_blur_f(im: Image.Image, r: int, passes: int = 3) -> Image.Image:
    """Box blur for mode F (Pillow's blur filters reject F). Three passes approximate a Gaussian."""
    if r <= 0:
        return im
    n = 2 * r + 1
    for _ in range(passes):
        for axis in (0, 1):
            acc = im
            for d in range(1, r + 1):
                a, b = (shift(im, d, 0), shift(im, -d, 0)) if axis == 0 else (shift(im, 0, d), shift(im, 0, -d))
                acc = fmath(lambda v: v["s"] + v["a"] + v["b"], s=acc, a=a, b=b)
            im = fmath(lambda v: v["s"] / n, s=acc)
    return im


def polar_maps(size: int, radius: float) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Per-pixel radius (in coin radii), reed phase (0..1, peaks on each reed) and a diagonal
    coordinate (-1 at the upper left to 1 at the lower right of the coin)."""
    c = (size - 1) / 2
    rr: list[float] = []
    reed: list[float] = []
    diag: list[float] = []
    for y in range(size):
        dy = y - c
        for x in range(size):
            dx = x - c
            rr.append(math.hypot(dx, dy) / radius)
            reed.append(0.5 + 0.5 * math.cos(REEDS * math.atan2(dy, dx)))
            diag.append((dx + dy) / (2 * radius))
    maps = []
    for data in (rr, reed, diag):
        im = Image.new("F", (size, size))
        im.putdata(data)
        maps.append(im)
    return maps[0], maps[1], maps[2]


def radial(r_img: Image.Image, fn) -> Image.Image:
    """Apply a scalar function of radius via an 8192-step lookup (r is 0..~1.5)."""
    steps = 8192
    table = [fn(i / steps * 1.5) for i in range(steps + 1)]
    idx = fmath(lambda v: v["r"] * (steps / 1.5), r=r_img).convert("I")
    out = Image.new("F", r_img.size)
    data = [table[min(steps, max(0, i))] for i in idx.get_flattened_data()]
    out.putdata(data)
    return out


def ss(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- relief


def relief_maps(size: int, radius: float, groove_grow: int) -> dict[str, Image.Image]:
    """Lay the half-length 阿草 out on the coin canvas and split it into F maps in 0..1.

    body: the raised silhouette, faded out just inside the rim so the flat crop at the bottom
    of the source never shows; groove: thin grey line art (eyes, mouth, nose, arms) to cut in;
    bow: the green bow tie, a low raised plate; form: the source's soft shading, used to round
    the body a little.
    """
    src = Image.open(SOURCE).convert("RGBA")
    flat = Image.new("RGBA", src.size, (255, 255, 255, 255))
    flat.alpha_composite(src)
    lum = flat.convert("L")
    r, g, b, alpha = src.split()

    # Green bow tie by hue, so its fill is a plate and not a pit.
    bow = ImageMath.lambda_eval(
        lambda v: ((v["g"] > v["r"] + 12) & (v["g"] > v["b"] + 5)) * 255, r=r, g=g, b=b
    ).convert("L")
    bow = ImageChops.multiply(bow.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1)), alpha)

    # The lines are thin and grey while the body carries broad grey shading, so take strokes as
    # pixels darker than their surroundings (a high-pass), plus anything plainly dark (the nose).
    local = lum.filter(ImageFilter.GaussianBlur(5))
    hp = ImageChops.subtract(local, lum).point(lambda v: round(255 * ss((v - 5) / 28)))
    dark = lum.point(lambda v: round(255 * ss((120 - v) / 60)))
    line = ImageChops.multiply(ImageChops.lighter(hp, dark), alpha)

    # Soft shading -> gentle form; the bow is excluded so it does not read as a dent.
    form_src = ImageChops.lighter(lum, bow)
    form = form_src.filter(ImageFilter.GaussianBlur(10)).point(lambda v: round(255 * ss((v - 185) / 65)))
    form = ImageChops.multiply(form, alpha)

    # Placement: source width spans FIG_W radii, source x FIG_CX sits on the centre line, the top of
    # the source sits FIG_TOP radii above the centre. The bottom runs past the rim and is faded out.
    k = FIG_W * radius / src.width
    w, h = round(src.width * k), round(src.height * k)
    c = (size - 1) / 2
    ox = round(c - FIG_CX * k)
    oy = round(c + FIG_TOP * radius)

    def place(im: Image.Image, grow: int = 0) -> Image.Image:
        im = im.resize((w, h), Image.Resampling.LANCZOS)
        if grow:
            im = im.filter(ImageFilter.MaxFilter(grow))
        out = Image.new("L", (size, size), 0)
        out.paste(im, (ox, oy))
        return fmath(lambda v: v["x"] / 255.0, x=out.convert("F"))

    return {
        "body": place(alpha),
        "groove": place(line, groove_grow),
        "bow": place(bow),
        "form": place(form),
    }


# ---------------------------------------------------------------- render


@dataclass(frozen=True)
class Style:
    """Per-size tuning. Small coins need wider, darker grooves to keep the face readable at 20px."""

    groove_grow: int = 0  # MaxFilter size applied to the stroke mask on the canvas (odd, 0 = off)
    groove_tone: float = 0.30  # extra darkening inside grooves (patina in the recesses)
    bow_tone: float = 0.10  # extra darkening on the bow tie
    field_tone: float = 0.16  # the recessed field is a little darker than the relief


def render_tone(out_size: int, ss_factor: int, style: Style) -> tuple[Image.Image, Image.Image]:
    """Shade the coin once; returns (tone L image 0..255, alpha L image), both at out_size."""
    size = out_size * ss_factor
    pad = 4 * ss_factor
    full = size + 2 * pad
    radius = size / 2 - ss_factor * 0.6
    r_img, reed, diag = polar_maps(full, radius)

    def rim_profile(r: float) -> float:
        # Field at 0; rim climbs over its inner bevel, stays high, then rounds off at the edge.
        up = ss((r - RIM_IN) / 0.035)
        down = ss((r - 0.975) / 0.045)
        return 1.0 * up - 0.75 * down

    rim = radial(r_img, rim_profile)
    inner_line = radial(r_img, lambda r: 0.22 * math.exp(-(((r - LINE_R) / 0.0085) ** 2)))
    # Reeds: fine radial grooves on the outer band of the rim.
    band = radial(r_img, lambda r: ss((r - 0.935) / 0.03))
    rim = fmath(lambda v: v["h"] - 0.28 * v["b"] * (1 - v["p"]), h=rim, b=band, p=reed)

    maps = relief_maps(full, radius, style.groove_grow)
    fade = radial(r_img, lambda r: 1.0 - ss((r - FADE_R[0]) / (FADE_R[1] - FADE_R[0])))
    blur = lambda im, k: box_blur_f(im, max(1, round(k * radius)))  # noqa: E731
    body = fmath(lambda v: v["b"] * v["f"], b=maps["body"], f=fade)
    body_soft = blur(body, 0.014)
    dome = blur(body, 0.12)
    groove_soft = fmath(lambda v: v["g"] * v["f"], g=blur(maps["groove"], 0.004), f=fade)
    bow_soft = fmath(lambda v: v["g"] * v["f"], g=blur(maps["bow"], 0.008), f=fade)
    form = fmath(lambda v: v["g"] * v["f"], g=blur(maps["form"], 0.01), f=body_soft)
    relief = fmath(
        lambda v: 0.70 * v["b"] + 0.95 * v["d"] + 0.30 * v["fo"] - 0.50 * v["g"] + 0.16 * v["bw"],
        b=body_soft, d=dome, fo=form, g=groove_soft, bw=bow_soft,
    )
    # The thin line inside the rim runs only across the bare field.
    rim = fmath(lambda v: v["r"] + v["l"] * (1 - v["b"]), r=rim, l=inner_line, b=body_soft)
    height = fmath(lambda v: (v["rim"] + v["rel"]) * v["k"], rim=rim, rel=relief, k=radius * 0.05)

    # Normals from central differences; light from the upper left.
    gx = fmath(lambda v: (v["a"] - v["b"]) / 2, a=shift(height, -1, 0), b=shift(height, 1, 0))
    gy = fmath(lambda v: (v["a"] - v["b"]) / 2, a=shift(height, 0, -1), b=shift(height, 0, 1))
    lx, ly, lz = -0.55, -0.62, 0.56
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    hx, hy, hz = lx, ly, lz + 1
    hn = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hn, hy / hn, hz / hn
    flat_d = lz
    flat_s = hz ** 24

    # Field mask: inside the rim and outside the relief.
    inside = radial(r_img, lambda r: 1.0 - ss((r - RIM_IN + 0.01) / 0.03))
    field = fmath(lambda v: v["i"] * (1 - v["b"]), i=inside, b=body_soft)
    st = style
    shade = fmath(
        lambda v: (
            lambda nl, nh: 0.66
            + 1.10 * (nl - flat_d)
            + 0.35 * ((nh ** 24) - flat_s)
            - 0.12 * v["sh"]
            - st.groove_tone * v["g"]
            - st.bow_tone * v["t"]
            - st.field_tone * v["f"]
        )(
            (-v["gx"] * lx - v["gy"] * ly + lz) / ((v["gx"] * v["gx"] + v["gy"] * v["gy"] + 1) ** 0.5),
            ((-v["gx"] * hx - v["gy"] * hy + hz) / ((v["gx"] * v["gx"] + v["gy"] * v["gy"] + 1) ** 0.5)).__abs__(),
        ),
        gx=gx, gy=gy, sh=diag, g=groove_soft, t=bow_soft, f=field,
    )
    shade = fmath(lambda v: v["s"] * 255, s=shade)
    tone_l = shade.convert("L").crop((pad, pad, pad + size, pad + size))  # convert clamps to 0..255

    # Alpha: the disk, with the reeds notching the silhouette very slightly.
    edge = fmath(lambda v: (1.0 - 0.012 * (1 - v["p"]) - v["r"]) * v["k"], p=reed, r=r_img, k=radius)
    alpha = fmath(lambda v: (v["e"] + 0.5) * 255, e=edge).convert("L").crop((pad, pad, pad + size, pad + size))

    tone_l = tone_l.resize((out_size, out_size), Image.Resampling.BOX)
    alpha = alpha.resize((out_size, out_size), Image.Resampling.BOX)
    return tone_l, alpha


def colourise(tone: Image.Image, alpha: Image.Image, metal: str) -> Image.Image:
    rgb = tone.convert("RGB").point(ramp_lut(PALETTES[metal]))
    rgb.putalpha(alpha)
    return rgb


def save(im: Image.Image, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=90, method=6)
    return path.stat().st_size


# ---------------------------------------------------------------- preview


def preview(path: Path, coin: Image.Image, coin64: Image.Image, badges: list[Image.Image]) -> None:
    font = ImageFont.load_default(size=13)
    # The UI shows the 64px file at 20 CSS px: 20 device px at 100% scaling, 40 on a 2x screen.
    small = coin64.resize((20, 20), Image.Resampling.LANCZOS)
    hidpi = coin64.resize((40, 40), Image.Resampling.LANCZOS)
    zoom = small.resize((80, 80), Image.Resampling.NEAREST)
    w, h = 980, 700
    sheet = Image.new("RGBA", (w, h), PAPER)
    ImageDraw.Draw(sheet).rectangle((0, h // 2, w, h), fill=INK)
    for row, (bg, fg) in enumerate(((PAPER, INK), (INK, PAPER))):
        y0 = row * (h // 2) + 30
        d = ImageDraw.Draw(sheet)
        x = 30
        for im, label in ((coin, "256"), (coin64, "64"), (hidpi, "20 @2x"), (small, "20"), (zoom, "20 x4")):
            sheet.alpha_composite(im, (x, y0 + (256 - im.height) // 2))
            d.text((x, y0 + 270), label, fill=fg, font=font)
            x += im.width + 36
        for i, (b, name) in enumerate(zip(badges, ("copper", "silver", "gold"))):
            bx = x + 20 + (i % 2) * 100
            by = y0 + 20 + (i // 2) * 120
            sheet.alpha_composite(b, (bx, by))
            sheet.alpha_composite(b.resize((20, 20), Image.Resampling.LANCZOS), (bx + 70, by + 22))
            d.text((bx, by + 70), name, fill=fg, font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, nargs="?", const=DEFAULT_PREVIEW)
    args = ap.parse_args()

    tone256, a256 = render_tone(256, 4, Style())
    # The 64px master cuts wider, darker grooves so the smile and bow tie survive the UI's 20px downscale.
    tone64, a64 = render_tone(64, 8, Style(groove_grow=7, groove_tone=0.6, bow_tone=0.35, field_tone=0.3))

    coin = colourise(tone256, a256, "gold")
    coin64 = colourise(tone64, a64, "gold")
    badges = [colourise(tone64, a64, m) for m in ("copper", "silver", "gold")]

    sizes = {"coin.webp": save(coin, OUT / "coin.webp"), "coin-64.webp": save(coin64, OUT / "coin-64.webp")}
    for i, b in enumerate(badges, 1):
        sizes[f"badge-{i}.webp"] = save(b, OUT / f"badge-{i}.webp")
    for name, n in sizes.items():
        print(f"{name:14} {n:6d} B")
    print(f"{'total':14} {sum(sizes.values()):6d} B")

    if args.preview:
        load = lambda p: Image.open(p).convert("RGBA")  # noqa: E731
        preview(
            args.preview,
            load(OUT / "coin.webp"),
            load(OUT / "coin-64.webp"),
            [load(OUT / f"badge-{i}.webp") for i in (1, 2, 3)],
        )
        print(f"preview -> {args.preview}")


if __name__ == "__main__":
    main()
