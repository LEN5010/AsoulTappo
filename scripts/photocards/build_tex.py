# Builds the textures of the photocards (官周小卡) from the specs next to this file, one JSON file per card, into tex/:
#   tex/<id>-front-base / tex/<back name>-back-base: what is printed.
#   tex/<id>-front-mat  / tex/<back name>-back-mat : R gloss, G foil (0.5 the dark tinted foil, 1 silver),
#     B on the front the printed small type, which lies over the frame's cross-hatching; unused on the back.
#   tex/cards.json: the cards. pack.py turns all of it into the client's assets.
# The frame is redrawn from measurements of the scan; only the art window, the names and the icons come from
# the enlarged scan, a solo back's name from the enlarged photo, and the event logo on the backs from the
# concert's key visual (logo.py). What a scan greys is put right: its paper, its lights and how full its colours are
# (tone.py, tone.json). Units are texels of the finished texture, whose short side is 1080. README.md describes the
# specs. Sources are not in git; PHOTOCARDS names the working directory, with src/ and tex/, and CJK_FONT the font of
# the small type (Noto Sans SC).
#   usage: build_tex.py [card id ...] [--backs]     all cards when none is named; --backs rebuilds the named cards' backs
import json
import math
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SS = 2   # working scale
VS = 4   # vector shapes are drawn at this scale, then reduced to SS

LATIN = ("/System/Library/Fonts/Avenir Next Condensed.ttc", 2)  # Demi Bold
CJK = os.environ.get("CJK_FONT", "NotoSansSC.ttf")
PRINT = np.array([24, 20, 22], np.float32)
SILVER = np.array([150, 142, 150], np.float32)   # the silver foil, away from the light

# The event logo and the line under it are the same artwork at the same size on every back. logo.py
# cuts both out, white on black at LOGO_SCALE px per texel.
LOGO, SUBTITLE, LOGO_SCALE = "logo.png", "logo-subtitle.png", 4

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ["PHOTOCARDS"])
SPECS, SOURCES, OUT = HERE / "specs", WORK / "src", WORK / "tex"
TONE_FILE = HERE / "tone.json"
TONE = json.loads(TONE_FILE.read_text()) if TONE_FILE.exists() else {}


def load_specs():
    """Every card's spec, with what it `extends` filled in. A file whose name starts with _ is only a base."""
    raw = {p.stem: json.loads(p.read_text()) for p in sorted(SPECS.glob("*.json"))}

    def resolve(name):
        spec = dict(raw[name])
        base = spec.pop("extends", None)
        return {**resolve(base), **spec} if base else spec

    return {name: resolve(name) for name in raw if not name.startswith("_")}


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a + (b - a) * t[..., None]


def clean(mask, sigma=0.7):
    """A mask taken from a photo or scan, with its pinholes closed and its edges drawn firm."""
    return smooth(0.32, 0.68, cv2.GaussianBlur(mask, (0, 0), sigma * SS))


def grow(mask, r):
    """A 0..1 mask widened by r texels."""
    k = int(round(r * SS)) * 2 + 1
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def foil_map(tinted, silver):
    """G of the material map: 0.5 on the tinted foil, rising to 1 on the silver."""
    return 0.5 * tinted + (1 - 0.5 * tinted) * silver


class Sheet:
    """Drawing helpers for one card size. Masks are float arrays at the working scale."""

    def __init__(self, size):
        self.W, self.H = size

    def blank(self):
        return np.zeros((self.H * SS, self.W * SS), np.float32)

    def ramp(self, step, colours):
        stops = np.array([[int(c[i:i + 2], 16) for i in (0, 2, 4)] for c in colours], np.float32)
        y = np.arange(self.H * SS, dtype=np.float32) / SS / step
        rows = np.stack([np.interp(y, np.arange(len(stops)), stops[:, k]) for k in range(3)], axis=1)
        # Rounded off, so the joins between the measured stops do not show as faint bands.
        k = np.exp(-0.5 * (np.arange(-120 * SS, 120 * SS + 1) / (40.0 * SS)) ** 2)
        k /= k.sum()
        pad = np.pad(rows, ((120 * SS, 120 * SS), (0, 0)), mode="edge")
        rows = np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(3)], axis=1).astype(np.float32)
        return np.repeat(rows[:, None, :], self.W * SS, axis=1)

    def shape(self, fn):
        im = Image.new("L", (self.W * VS, self.H * VS), 0)
        fn(ImageDraw.Draw(im), VS)
        return np.asarray(im.resize((self.W * SS, self.H * SS), Image.BOX), np.float32) / 255

    def rrect(self, x0, y0, x1, y1, r):
        return self.shape(lambda d, k: d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], radius=r * k, fill=255))

    def crosses(self, centres, half=12.4, width=3.6):
        def fn(d, k):
            for cx, cy in centres:
                for s in (1, -1):
                    d.line([((cx - half) * k, (cy - s * half) * k), ((cx + half) * k, (cy + s * half) * k)], fill=255, width=round(width * k))
        return self.shape(fn)

    def sparkles(self, grid, blocks, rmax=10.8):
        """Alpha of the sparkle field. blocks: (corner, columns, rows[, largest half-size]); size falls off with
        distance from that corner."""
        gx, gy, px, py = grid
        W, H = self.W, self.H
        a = self.blank()
        for i in range(int((W - gx) / px) + 1):
            for j in range(int((H - gy) / py) + 1):
                x, y = gx + px * i, gy + py * j
                size, top = 0.0, rmax
                for corner, cols, rows, *largest in blocks:
                    u = (x if corner == "tl" else W - x) / (cols * px)
                    v = (y if corner == "tl" else H - y) / (rows * py)
                    s = min(1.0, 1.3 * (1 - math.hypot(u, v)))
                    if s > size:
                        size, top = s, (largest[0] if largest else rmax)
                if size <= 0.05:
                    continue
                R = top * (0.2 + 0.8 * size)
                p = 1.0 - 0.42 * size  # a diamond when small, a four-point star when large
                x0, x1 = max(0, int((x - R - 2) * SS)), min(W * SS, int((x + R + 2) * SS) + 1)
                y0, y1 = max(0, int((y - R - 2) * SS)), min(H * SS, int((y + R + 2) * SS) + 1)
                if x0 >= x1 or y0 >= y1:
                    continue
                xx = np.abs((np.arange(x0, x1) + 0.5) / SS - x)[None, :]
                yy = np.abs((np.arange(y0, y1) + 0.5) / SS - y)[:, None]
                f = (xx ** p + yy ** p) ** (1 / p)
                a[y0:y1, x0:x1] = np.maximum(a[y0:y1, x0:x1], np.clip((R - f) * SS + 0.5, 0, 1))
        return a

    def text(self, text, font, box, tracking=0.0, vertical=False):
        """`text` set in `font` and fitted exactly into box (x0, y0, x1, y1). Vertical text reads upward."""
        x0, y0, x1, y1 = box
        probe = Image.new("L", (4000, 400), 0)
        d = ImageDraw.Draw(probe)
        x = 20.0
        for ch in text:
            d.text((x, 60), ch, font=font, fill=255)
            x += d.textlength(ch, font=font) + tracking
        glyphs = probe.crop(probe.getbbox())
        tw, th = round((x1 - x0) * VS), round((y1 - y0) * VS)
        if vertical:
            glyphs = glyphs.resize((th, tw), Image.LANCZOS).rotate(90, expand=True)
        else:
            glyphs = glyphs.resize((tw, th), Image.LANCZOS)
        im = Image.new("L", (self.W * VS, self.H * VS), 0)
        im.paste(glyphs, (round(x0 * VS), round(y0 * VS)))
        return np.asarray(im.resize((self.W * SS, self.H * SS), Image.BOX), np.float32) / 255

    def regions(self, mask, boxes):
        m = np.zeros_like(mask)
        for x0, y0, x1, y1 in boxes:
            sl = (slice(int(y0 * SS), int(y1 * SS)), slice(int(x0 * SS), int(x1 * SS)))
            m[sl] = mask[sl]
        return m

    def source(self, path):
        im = cv2.cvtColor(cv2.imread(str(SOURCES / path)), cv2.COLOR_BGR2RGB)
        return cv2.resize(im, (self.W * SS, self.H * SS), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)

    def save(self, name, rgb, lossless=False):
        im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((self.W, self.H), Image.LANCZOS)
        if lossless:
            im.save(OUT / f"{name}.png", optimize=True)
        else:
            im.save(OUT / f"{name}.webp", quality=93, method=6)
        print(name, im.size)


def pill(sheet, spec):
    """A capsule: its outer shape, the thin foil ring along its edge, the foil bar inside, and the bar's lettering."""
    x0, y0, x1, y1 = spec["box"]
    v = spec["vertical"]
    out = sheet.rrect(x0, y0, x1, y1, 25)
    ring = np.clip(out - sheet.rrect(x0 + 3.2, y0 + 3.2, x1 - 3.2, y1 - 3.2, 22), 0, 1)
    ix, iy = (10.8, 9.2) if v else (9.2, 10.8)
    inner = sheet.rrect(x0 + ix, y0 + iy, x1 - ix, y1 - iy, 15)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (8, 52.8) if v else (52.8, 8)
    text = sheet.text(spec["text"], ImageFont.truetype(LATIN[0], 120, index=LATIN[1]), (cx - hw, cy - hh, cx + hw, cy + hh), tracking=30, vertical=v)
    return out, ring, inner, text * inner


def photo_masks(photo, solid=0):
    """What a photo of a back shows lighter and darker than the ground around it.

    The ground is a wide median, which a large filled shape drags down to its own colour, leaving the shape
    hollow. `solid` is the width in texels of the largest filled dark shape: with it the ground is also taken
    from the photo with dark shapes up to that width closed over. Only for backs that need it, as it also
    marks every soft shadow as dark."""
    pl = photo.mean(axis=2)
    soft = cv2.GaussianBlur(cv2.medianBlur(np.clip(pl, 0, 255).astype(np.uint8), 151).astype(np.float32), (0, 0), 12)
    ground = soft
    if solid:
        k = int(solid * SS) * 2 + 1
        closed = cv2.morphologyEx(pl, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        ground = np.maximum(soft, cv2.GaussianBlur(closed, (0, 0), 12))
    return clean(smooth(7, 20, pl - soft)), clean(smooth(14, 40, ground - pl))


def stamp(sheet, name, at, centred=False):
    """One of the masks cut by logo.py, set down on `sheet` with its top left corner or its centre at `at`."""
    im = cv2.imread(str(SOURCES / name), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
    if SS != LOGO_SCALE:
        im = cv2.resize(im, None, fx=SS / LOGO_SCALE, fy=SS / LOGO_SCALE, interpolation=cv2.INTER_AREA)
    h, w = im.shape
    x, y = at[0] * SS, at[1] * SS
    if centred:
        x, y = x - w / 2, y - h / 2
    x, y = round(x), round(y)
    m = sheet.blank()
    m[y:y + h, x:x + w] = im
    return m


def decoded(c):
    """sRGB, 0 to 1, as light."""
    return np.where(c <= 0.04045, c / 12.92, ((np.maximum(c, 0) + 0.055) / 1.055) ** 2.4)


def encoded(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


LMS = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
LAB = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


def oklab(light):
    return np.cbrt(np.maximum(light @ LMS.T, 0)) @ LAB.T


def unlab(lab):
    return (lab @ np.linalg.inv(LAB).T) ** 3 @ np.linalg.inv(LMS).T


def paper(card):
    """The scan's paper, 0 to 1: what the card's ramp ends in."""
    return np.array([int(card["ramp"][1][-1][i:i + 2], 16) for i in (0, 2, 4)]) / 255


def balanced(light, white):
    """The scan's whites as the design has them; what is dark keeps its hue."""
    return light * (1 + (np.asarray(white) - 1) * smooth(0.3, 0.85, oklab(light)[..., :1]))


def toned(rgb, card, white=(1.0, 1.0, 1.0), light=(0.0, 1.0)):
    """A scan's colours as they are printed: the paper white, the lightness taken along a line, colours as full as the
    design has them, by their hue. What would come out lighter than white is drawn in softly. tone.py measured it."""
    gain = np.array(TONE["gain"])
    lab = oklab(balanced(decoded(np.asarray(rgb) / 255) / decoded(paper(card)), white))
    at = np.arctan2(lab[..., 2], lab[..., 1]) / (2 * np.pi) % 1 * len(gain)
    full = np.interp(at, np.arange(len(gain) + 1), np.append(gain, gain[0]))
    y = light[0] + light[1] * lab[..., 0]
    knee = 0.95
    y = np.where(y > knee, knee + (1 - knee) * (1 - np.exp(-np.maximum(y - knee, 0) / (1 - knee))), y)
    lab = np.stack([y, lab[..., 1] * full, lab[..., 2] * full], axis=-1)
    return (encoded(unlab(lab)) * 255).astype(np.float32)


def ground(sheet, card):
    """The frame's gradient and the colour of its dark sparkles, as printed."""
    return sheet.ramp(card["ramp"][0], TONE["frame"][card["back"]["name"]]), toned(np.float32(card["spark_dark"]), card)


def build_front(card_id, card):
    """The front of one card."""
    sheet = Sheet(card["size"])
    tint = np.float32(card["tinted"])
    latin = ImageFont.truetype(LATIN[0], 120, index=LATIN[1])
    cjk = ImageFont.truetype(CJK, 120)
    cjk.set_variation_by_axes([560])

    # ------------------------------------------------------------ front
    sr = sheet.source(card["source"])
    # Names and icons are the same on every card of a member, so they may come from one reference scan.
    lettering = sheet.source(card["frame_source"]) if card.get("frame_source", card["source"]) != card["source"] else sr
    dark = smooth(150, 80, lettering.mean(axis=2))   # 1 on the dark elements of the enlarged scan

    bg, spark_dark = ground(sheet, card)
    blocks = card["sparkles"]
    light = sheet.sparkles(card["grid"], [b for b in blocks if b[0] == "tl"])
    dim = sheet.sparkles(card["grid"], [b for b in blocks if b[0] == "br"])
    frame = mix(mix(bg, np.float32([255, 255, 255]), 0.62 * light), spark_dark, 0.85 * dim)

    wx0, wy0, wx1, wy1, wr = card["window"]
    window = sheet.rrect(wx0, wy0, wx1, wy1, wr)
    bar = sheet.rrect(*card["bar"]["box"], 20)
    bar_text = sheet.text(card["bar"]["text"], latin, card["bar"]["text_box"], tracking=card["bar"]["tracking"]) * bar
    pills = [pill(sheet, p) for p in card["pills"]]
    pill_out = np.maximum.reduce([p[0] for p in pills])
    names = clean(sheet.regions(dark, card["names"]))
    icons = clean(sheet.regions(dark, card["icons"]))
    # Under a solo card's name sit two copies of the member's small icon, the left in plain black print and the
    # right in the foil of the name. Both are cut from whichever of the two the scan shows more cleanly.
    twin_print, twin_foil = sheet.blank(), sheet.blank()
    if "twin" in card:
        twin = card["twin"]
        x0, y0, x1, y1 = [int(v * SS) for v in twin["from"]]
        pad = 8 * SS
        shape = clean(dark[y0 - pad:y1 + pad, x0 - pad:x1 + pad])[pad:-pad, pad:-pad]
        for at, to in ((twin["print"], twin_print), (twin["foil"], twin_foil)):
            ax, ay = round(at[0] * SS), round(at[1] * SS)
            to[ay:ay + y1 - y0, ax:ax + x1 - x0] = shape
    marks = sheet.crosses(card["marks"])
    small = sheet.blank()
    for line in card["lines"]:
        # A label, a dash and an account name; the offsets default to those of "MEMBER OF A-SOUL".
        x, y = line["x"], line["y"]
        d0, d1 = line.get("dash", (218.9, 272.9))
        hx = x + line.get("handle_x", 286.4)
        small = np.maximum.reduce([
            small,
            sheet.text(line.get("label", "MEMBER OF A-SOUL"), latin, (x, y, x + line.get("label_w", 203.8), y + 20)),
            sheet.rrect(x + d0, y + 9.1, x + d1, y + 11.7, 0),
            sheet.text(line["handle"], cjk, (hx, y - 2.5, hx + line["handle_w"], y + 23.5)),
        ])

    art_mask = window * (1 - pill_out) * (1 - bar)
    tinted = np.clip(np.maximum.reduce([bar, names, icons, twin_foil] + [p[1] for p in pills] + [p[2] for p in pills]), 0, 1)
    silver = np.clip(np.maximum.reduce([marks, bar_text] + [p[3] for p in pills]), 0, 1)

    # The scanned bar and capsules do not sit exactly under the redrawn ones; paint the art over a band around
    # each, so no sliver of the scanned outline shows beside the new shape.
    around = (np.maximum(grow(pill_out, 7), grow(bar, 6)) > 0.5).astype(np.uint8) * 255
    art = cv2.inpaint(np.clip(sr, 0, 255).astype(np.uint8), around, 6 * SS, cv2.INPAINT_TELEA).astype(np.float32)
    art = toned(art, card, TONE["white"][card_id], TONE["light"][card_id])
    base = mix(frame, art, window)
    base = mix(base, bg, pill_out)
    ink = np.clip(twin_print + small, 0, 1)
    base = mix(base, PRINT, ink)
    base = mix(mix(base, tint, tinted), SILVER, silver)
    sheet.save(f"{card_id}-front-base", base)
    sheet.save(f"{card_id}-front-mat", np.stack([art_mask, foil_map(tinted, silver), ink], axis=2) * 255, lossless=True)


def build_back(card):
    """A card's back. Cards share backs by name: every landscape card has one, and so has each member."""
    sheet = Sheet(card["size"])
    tint = np.float32(card["tinted"])
    bg, spark_dark = ground(sheet, card)
    back = card["back"]
    # The lettering is one reflective print. Printed flat it reads pale on the dark end of the card and deep on
    # the light end: `logo` collects the pale parts, `ident` the deep parts. A part is either taken from a
    # photo of this back (`lighter`, `darker`: regions of what the photo shows lighter or darker than the
    # ground), drawn (`marks`: crosses), or the event's artwork set down at a point (`logo`: the top left corner
    # of the event logo's box; `subtitle`: the centre of the line under it).
    parts = {"pale": [], "deep": []}
    if "source" in back:
        lighter, darker = photo_masks(sheet.source(back["source"]), back.get("solid", 0))
        parts["pale"].append(sheet.regions(lighter, back.get("lighter", [])))
        parts["deep"].append(sheet.regions(darker, back.get("darker", [])))
    ink = back.get("logo_ink", "pale")   # which of the two the logo and its subtitle are
    parts[ink] += [stamp(sheet, LOGO, back["logo"]), stamp(sheet, SUBTITLE, back["subtitle"], centred=True)]
    for tone, centres in back.get("marks", {}).items():
        parts[tone].append(sheet.crosses(centres))
    logo, ident = (np.clip(np.maximum.reduce(parts[t] + [sheet.blank()]), 0, 1) for t in ("pale", "deep"))
    bfoil = np.maximum(logo, ident)

    blocks = back["sparkles"]
    grid = back.get("grid", card["grid"])
    light = sheet.sparkles(grid, [b for b in blocks if b[0] == "tl"])
    dim = sheet.sparkles(grid, [b for b in blocks if b[0] == "br"])
    bbase = mix(mix(bg, np.float32([255, 255, 255]), 0.6 * light), spark_dark, 0.85 * dim)
    bbase = mix(mix(bbase, tint, ident), SILVER, logo)
    sheet.save(f"{back['name']}-back-base", bbase)
    gloss = np.maximum(light, dim) * (1 - bfoil)
    sheet.save(f"{back['name']}-back-mat", np.stack([gloss, foil_map(ident, logo), sheet.blank()], axis=2) * 255, lossless=True)


def write_list(specs):
    """tex/cards.json: every card whose textures exist, in the order the page shows them."""
    cards = []
    for card_id, card in sorted(specs.items(), key=lambda kv: (kv[1].get("order", 999), kv[0])):
        if not (OUT / f"{card_id}-front-base.webp").exists():
            continue
        back = card.get("back")
        cards.append({
            "id": card_id, "label": card.get("label", card_id), "size": card["size"],
            "back": back["name"] if back and (OUT / f"{back['name']}-back-base.webp").exists() else None,
            "foil": card["foil"], "print": card["print"],
        })
    rows = ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in cards)
    # `built` changes with every build, so a page never shows a texture the browser kept from an earlier one.
    (OUT / "cards.json").write_text(f'{{"built": {int(time.time())}, "cards": [\n{rows}\n]}}\n')
    print("cards.json", len(cards))


if __name__ == "__main__":
    specs = load_specs()
    ids = [a for a in sys.argv[1:] if a != "--backs"]
    backs = set()
    for card_id in ids or specs:
        card = specs[card_id]
        build_front(card_id, card)
        # Backs are shared, so one is built only when it is missing, when --backs asks, or when every card is built.
        name = card["back"]["name"] if card.get("back") else None
        if name and name not in backs and ("--backs" in sys.argv or not ids or not (OUT / f"{name}-back-base.webp").exists()):
            backs.add(name)
            build_back(card)
    write_list(specs)
