# Cuts the event logo out of the concert's key visual, which there is twice at 7500 x 4220, once with the logo and once
# without, and the two lines of type that go with it on the cards out of the sale poster. Writes into src/:
#   logo.png           the logo and the small line under it, covering the box LOGO_BOX of a portrait back, white on
#                      black at K px per texel
#   logo-subtitle.png  the line of Chinese type with its two stars, centred in the image, likewise
#   logo-title.png     the logo as the key visual has it, in crystal and with its flares, on nothing
# build_tex.py sets the first two down on every back, box.py prints them on the box. The poster puts the subtitle lower
# than the cards do, so it is kept apart from the logo.
# Reads src/kv/{titled,clean}/poster.jpg, src/poster/sale-details.jpg and src/logo-coarse.png, an earlier and coarser
# cut (2 px per texel) that says where on the cards the logo lies and roughly what belongs to it.
#   usage: logo.py [--check out.png]     --check also writes the coarse cut above the new one
import os
import sys
from pathlib import Path

import cv2
import numpy as np

SOURCES = Path(os.environ["PHOTOCARDS"]) / "src"
K = 4                                 # px per texel, as LOGO_SCALE in build_tex.py
LOGO_BOX = (440, 112, 1062, 296)      # the logo's box on a portrait back, in texels
W, H = (LOGO_BOX[2] - LOGO_BOX[0]) * K, (LOGO_BOX[3] - LOGO_BOX[1]) * K

# The part of the key visual with the logo. Every point below is a pixel of it.
CROP = (1800, 2640, 5640, 3760)
# Where one of its pixels lies in the coarse cut, fitted to it (findTransformECC; the two are the same drawing).
TO_COARSE = np.float32([[0.30911, 0, 6.218], [0, 0.30911, 21.367]])
# The same for a pixel of the sale poster: coarse = POSTER_SCALE * poster + POSTER_SHIFT.
POSTER_SCALE, POSTER_SHIFT = 1.140, (-15.0, 14.0 - 1.140 * 1250)
SMALL = (380, 302, 800, 358)          # the small line of Latin type, in the coarse cut
SUBTITLE = (200, 396, 1000, 468)      # the line of Chinese type, below it

# How bright the logo is at least, and where flares or hair behind it ask for more: x0, y0, x1, y1, brightness.
BRIGHT = 118
BRIGHTER = [
    (1430, 340, 1905, 760, 170), (2820, 395, 2875, 505, 150), (3060, 355, 3112, 420, 170), (1120, 150, 1184, 216, 178),
    (1152, 418, 1208, 470, 196), (1505, 290, 1531, 322, 205), (1340, 390, 1418, 600, 178), (1900, 566, 1924, 588, 235),
    (512, 748, 596, 778, 188),
]
# Level streaks of light across 间: their rows, and the columns they are looked for in.
STREAKS, STREAK_X = [(506, 524), (568, 586)], (1430, 1905)
# The flares: centre, and how far their glow and rays reach.
FLARES = [(461, 743, 130, 150), (3081, 206, 150, 165)]
GLOWS = [(461, 743, 150), (3081, 206, 165), (2425, 338, 190), (1658, 545, 230)]
# The burst in 共, whose edges are straight, and the room around it that holds nothing else of the logo.
BURST = [
    (2414.7, 200), (2420, 335.5), (2499.5, 284.5), (2443.5, 355.2), (2569.5, 378.8), (2432.5, 402), (2475, 475.8),
    (2408.5, 423.8), (2398, 455), (2390, 510), (2352, 510), (2363, 455), (2363.3, 440), (2361.8, 424.3), (2284.3, 474.5),
    (2343.8, 402.5), (2267.5, 388.8), (2222, 388.8), (2222, 372), (2349.5, 355.8), (2309.3, 285), (2373.3, 333.8),
]
BURST_ROOM = [
    (2226, 366), (2250, 300), (2300, 262), (2380, 190), (2440, 190), (2500, 262), (2545, 330), (2578, 372), (2578, 390),
    (2540, 430), (2490, 490), (2400, 486), (2340, 486), (2276, 486), (2250, 430), (2226, 400),
]
# Outlines a flare hides, or where the metal is as dark as the picture: smooth lines through points read off it.
# 鸣's first stroke, under its flare, and the stroke below it.
WEDGE = [(2955, 309), (2964, 304), (2980, 295), (3000, 284.8), (3020, 273.6), (3040, 258), (3060, 240), (3076, 224), (3087, 212.3), (3098, 198.5)]
WEDGE_LEFT = [(3012, 197.6), (3001.4, 199.6), (2994, 214), (2985, 233), (2975, 251), (2962, 272)]
BROW = [(2975, 303.6), (3000, 298), (3020, 294.2), (3040, 291.1), (3060, 289.1), (3080, 287.7), (3100, 287.3), (3116, 288), (3132, 292), (3146, 298.5)]
BROW_FOOT = [(3146, 306), (3060, 306), (2990, 308), (2975, 310)]
JOINT = [(2952, 299.5), (2975, 299.5), (3005, 296.5), (3005, 304), (2975, 310), (2952, 312)]
# The loop 此 begins with.
LOOP_OUT = [
    (415, 832), (410.2, 812), (409.5, 800), (410.6, 788), (413.3, 778.3), (417.5, 768.3), (422.5, 760), (429.2, 751.7), (435, 746.3),
    (442, 741.3), (451, 737), (462.5, 733.2), (480, 730.6), (488.3, 729.4), (499, 728.7), (513, 729.7), (540, 735), (560, 739.5),
]
LOOP_IN = [(560, 753.5), (545, 751.2), (531, 752), (520, 755), (509, 761), (500, 768.2), (492, 777), (486.5, 788), (483, 800), (482, 815), (482.6, 832)]
# What is above the arms of the star in 间.
STAR_LEFT = [(1639, 501.5), (1630, 515.5), (1622.5, 524.5), (1610, 532.3), (1595, 537.8), (1580, 541), (1560, 543.4), (1550, 544.2)]
STAR_RIGHT = [(1664, 501.5), (1666.3, 512.5), (1670.3, 520), (1677.5, 526.8), (1687.5, 532.4), (1700, 537.3), (1720, 541.6), (1740, 544.2), (1749, 544.8)]
# 此's last sweep, the inner edge of the stroke before it, the hairline in 鸣.
SWEEP_IN = [(1126, 953), (1140, 949), (1160, 940), (1180, 930.6), (1200, 918.4), (1220, 903.6), (1240, 887.4), (1250, 878.4), (1260, 866.4), (1268, 856), (1276, 846), (1284, 834.4)]
SWEEP_OUT = [(1330, 838), (1320, 850), (1300, 871), (1280, 889), (1260, 903.6), (1240, 918), (1220, 930), (1200, 940.4), (1180, 950), (1160, 958), (1140, 964.4), (1126, 968)]
INNER = [(1106, 630), (1102, 650), (1098, 662), (1094, 682), (1090, 702), (1087.4, 720), (1085, 736), (1083, 746), (1082.4, 760), (1084, 772), (1088, 782)]
HAIR_OUT = [
    (2990, 428), (2984.4, 442.5), (2980.6, 452.5), (2977.5, 461.3), (2976, 470), (2976.5, 476.3), (2979.4, 485), (2983.8, 493.1),
    (2990, 500.6), (3000, 508.1), (3010, 512.1), (3020, 514.1), (3031, 514.8),
]
HAIR_IN = [
    (3034, 508.6), (3030, 509.8), (3020, 509.6), (3010, 507.8), (3000, 503.1), (2992.5, 497.5), (2986.3, 489.4), (2983.1, 482.5),
    (2982.3, 476.3), (2983.1, 471.3), (2985, 465.6), (2988.8, 460), (2995, 455), (3003.8, 451.3), (3012.5, 448.8), (3022, 440),
]
# The pulse runs out: to the right it is drawn, to the left it fades as the picture has it (row, reach).
PULSE_RIGHT, PULSE_LEFT = [(3732, 563.2), (3836, 567.6), (3732, 572.2)], (567.5, 160)
# Cracks in the metal that run through to both edges: x0, y0, x1, y1, radius.
CRACKS = [(1736, 536, 1806, 625, 7), (640, 560, 760, 700, 4)]
# Two stars whose points thin to nothing: centre, reach.
POINTS = [(739, 264, 78), (3280, 875, 108)]
# On the cards the two flares are printed as small stars: half width and half height, in the coarse cut.
STAMPED = (18, 24)
TITLE_W = 1500


def disc(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def curve(points, n=24):
    """A smooth line through the points (Catmull-Rom)."""
    p = np.float32(points)
    p = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = []
    for a, b, c, d in zip(p, p[1:], p[2:], p[3:]):
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (3 * b - a - 3 * c + d) * t ** 3))
    return list(out) + [p[-2]]


def fill(mask, points, value=1):
    cv2.fillPoly(mask, [np.round(np.float32(points) * 16).astype(np.int32)], value, cv2.LINE_8, 4)


def key_visual(which):
    x0, y0, x1, y1 = CROP
    return cv2.imread(str(SOURCES / "kv" / which / "poster.jpg"))[y0:y1, x0:x1].astype(np.float32)


def components(mask, connectivity, wanted):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=connectivity)
    return np.isin(labels, [i for i in range(1, n) if wanted(stats[i, cv2.CC_STAT_AREA])])


def cut(titled, clean):
    """Coverage of the logo, 0..1, at the size of the key visual."""
    h, w = titled.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    low, ground = titled.min(axis=2), clean.max(axis=2)
    coarse = cv2.imread(str(SOURCES / "logo-coarse.png"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
    coarse[300:, 380:800] = 0   # its small line
    guide = cv2.warpAffine(coarse, TO_COARSE, (w, h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP)

    need = np.full((h, w), BRIGHT, np.float32)
    for x0, y0, x1, y1, v in BRIGHTER:
        need[y0:y1, x0:x1] = v
    near = cv2.dilate((guide > 0.4).astype(np.uint8), disc(9)) > 0
    m = ((low - ground > 22) & (low > need) & near).astype(np.uint8)
    for y0, y1 in STREAKS:
        x0, x1 = STREAK_X
        m[y0:y1, x0:x1] = cv2.morphologyEx(m[y0 - 20:y1 + 20, x0:x1], cv2.MORPH_OPEN, np.ones((11, 1), np.uint8))[20:-20]

    # `drawn`: where the edge is drawn here, not found.
    drawn = np.zeros_like(m)
    fill(drawn, BURST_ROOM)
    m[drawn > 0] = 0
    fill(m, BURST)
    (ax, ay, ar, _), (bx, by, br, _) = FLARES
    lit_a = ((xx - ax) ** 2 + (yy - ay) ** 2 < ar ** 2) & (yy < 800) & (xx < 545)
    lit_b = ((xx - bx) ** 2 + (yy - by) ** 2 < br ** 2) & (yy < 300) & (xx > 2985)
    m[lit_a | lit_b] = 0
    fill(m, curve(WEDGE) + WEDGE_LEFT)
    fill(m, curve(BROW) + BROW_FOOT)
    fill(m, JOINT)
    m[308:345, 3060:3082] = 0   # a ray of the flare
    fill(m, curve(LOOP_OUT) + curve(LOOP_IN))
    fill(m, [(1550, 503), (1637, 503)] + curve(STAR_LEFT), 0)
    fill(m, [(1749, 503), (1664.5, 503)] + curve(STAR_RIGHT), 0)
    fill(m, curve(SWEEP_IN) + curve(SWEEP_OUT))
    fill(m, curve(HAIR_OUT) + curve(HAIR_IN))
    fill(m, curve(INNER) + [(1060, 782), (1060, 630)])
    fill(m, PULSE_RIGHT)
    for x0, y0, x1, y1, r in CRACKS:
        m[y0:y1, x0:x1] = cv2.morphologyEx(m[y0:y1, x0:x1], cv2.MORPH_CLOSE, disc(r))
    drawn[lit_a | lit_b] = 1
    for x0, y0, x1, y1 in ((1548, 500, 1752, 548), (1124, 830, 1332, 970), (2970, 440, 3034, 517), (3732, 555, w, 580), (1070, 655, 1106, 775)):
        drawn[y0:y1, x0:x1] = 1

    # Dark flecks of the metal, and dust.
    m[components(1 - m, 4, lambda area: area < 1500)] = 1
    m = components(m, 8, lambda area: area > 260).astype(np.uint8)

    # The edge to a fraction of a pixel: how far it lies between what is inside and what is outside next to it.
    def around(mask, sigma):
        weight = cv2.GaussianBlur(mask, (0, 0), sigma)
        return cv2.GaussianBlur(low * mask, (0, 0), sigma) / np.maximum(weight, 1e-4), weight
    inside, weight = around(cv2.erode(m, disc(3)).astype(np.float32), 5)
    outside, _ = around(1 - cv2.dilate(m, disc(3)).astype(np.float32), 4)
    inside = np.where(weight > 0.004, inside, cv2.dilate(low, disc(4)))   # a hairline has no inside of its own
    inside = np.maximum(inside, outside + 30)
    found = np.clip(((low - outside) / (inside - outside) - 0.5) * 1.25 + 0.5, 0, 1)
    band = (cv2.dilate(m, disc(3)) > 0) & (cv2.erode(m, disc(3)) == 0)
    alpha = np.where(band, found, m.astype(np.float32))
    # A dark fleck of the metal at the edge is inside all the same.
    alpha = np.maximum(alpha, np.clip(cv2.distanceTransform(m, cv2.DIST_L2, 5) - 1.6, 0, 1))
    alpha = np.where(drawn > 0, cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.9), alpha)

    # What fades out or thins to nothing.
    soft = np.clip((low - ground - 14) / np.maximum(238 - ground, 1), 0, 1)
    row, reach = PULSE_LEFT
    alpha = np.maximum(alpha, soft * np.clip((9 - np.abs(yy - row)) / 2, 0, 1) * (xx < reach))
    for cx, cy, reach in POINTS:
        arm = (np.minimum(np.abs(xx - cx), np.abs(yy - cy)) < 9) & (np.abs(xx - cx) + np.abs(yy - cy) < reach)
        alpha = np.maximum(alpha, np.where(arm, soft, 0))
    return alpha.astype(np.float32)


def title(titled, clean, alpha):
    """The logo in the key visual's own crystal, with its flares (BGRA)."""
    h, w = alpha.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # Under the soft edge lies the colour of the metal inside it.
    core = cv2.erode((alpha > 0.98).astype(np.float32), disc(1))
    weight = cv2.GaussianBlur(core, (0, 0), 2.2)[..., None]
    metal = np.where(weight > 0.02, cv2.GaussianBlur(titled * core[..., None], (0, 0), 2.2) / np.maximum(weight, 1e-4), np.maximum(titled, 225))
    metal = np.where(core[..., None] > 0, titled, metal)
    # The flares are light on top of the picture.
    glow = np.clip(((titled - clean) / np.maximum(255 - clean, 8)).min(axis=2), 0, 1)
    glow = np.clip((glow - 0.045) / 0.955, 0, 1)
    room = np.zeros((h, w), np.float32)
    for cx, cy, r in GLOWS:
        room = np.maximum(room, np.clip((r - np.hypot(xx - cx, yy - cy)) / (r * 0.55), 0, 1) ** 1.5)
    for cx, cy, _, r in FLARES:
        level = np.clip(1 - ((xx - cx) / r) ** 2, 0, 1) * np.clip(1.4 - np.abs(yy - cy - (xx - cx) * 0.07) / 12, 0, 1)
        upright = np.clip(1 - ((yy - cy) / r) ** 2, 0, 1) * np.clip(1.4 - np.abs(xx - cx + (yy - cy) * 0.09) / 12, 0, 1)
        room = np.maximum.reduce([room, level, upright])
    whole = np.maximum(alpha, glow * room)
    share = np.where(whole > 0, alpha / np.maximum(whole, 1e-4), 0)[..., None]
    colour = metal * share + np.float32([255, 250, 252]) * (1 - share)
    small = cv2.resize(np.dstack([colour * whole[..., None], whole * 255]), (TITLE_W, round(h * TITLE_W / w)), interpolation=cv2.INTER_AREA)
    a = small[..., 3:]
    return np.dstack([np.clip(np.where(a > 0, small[..., :3] * 255 / np.maximum(a, 1e-3), 255), 0, 255), a]).round().astype(np.uint8)


def printed(alpha):
    """The logo in its box of a back, with the flares as stars."""
    up = np.diag([K, K, 1.0]) @ np.vstack([TO_COARSE, [0, 0, 1]])   # twice K px per texel
    m = cv2.resize(cv2.warpAffine(alpha, up[:2], (W * 2, H * 2), flags=cv2.INTER_CUBIC), (W, H), interpolation=cv2.INTER_AREA)
    yy, xx = np.mgrid[0:H * 4, 0:W * 4].astype(np.float32)
    f = K / 2 * 4
    for cx, cy, _, _ in FLARES:
        x, y = TO_COARSE @ np.array([cx, cy, 1.0]) * f
        star = (np.abs((xx - x) / (STAMPED[0] * f)) ** 0.55 + np.abs((yy - y) / (STAMPED[1] * f)) ** 0.55 < 1).astype(np.float32)
        m = np.maximum(m, cv2.resize(star, (W, H), interpolation=cv2.INTER_AREA))
    return np.clip(m, 0, 1)


def line(box, middle, floor):
    """A line of type of the sale poster, [box] in the coarse cut's px, drawn sharp: a stroke's edge is where it is
    [middle] as bright as its core."""
    x0, y0, x1, y1 = box
    poster = cv2.imread(str(SOURCES / "poster/sale-details.jpg")).min(axis=2).astype(np.float32)
    px = lambda x: int((x - POSTER_SHIFT[0]) / POSTER_SCALE)
    py = lambda y: int((y - POSTER_SHIFT[1]) / POSTER_SCALE)
    X, Y = px(x0) - 40, py(y0) - 40
    c = poster[Y:py(y1) + 40, X:px(x1) + 40]
    ground = cv2.GaussianBlur(cv2.morphologyEx(c, cv2.MORPH_OPEN, disc(12)), (0, 0), 6)
    a = np.clip((c - ground - 10) / (240 - ground), 0, 1)
    a /= np.maximum(cv2.GaussianBlur(cv2.dilate(a, np.ones((5, 5))), (0, 0), 1.2), floor)
    f, s = K / 2, 3
    w, h = int((x1 - x0) * f), int((y1 - y0) * f)
    k = POSTER_SCALE * f * s
    to = np.float32([[k, 0, k * X + (POSTER_SHIFT[0] - x0) * f * s], [0, k, k * Y + (POSTER_SHIFT[1] - y0) * f * s]])
    up = cv2.GaussianBlur(cv2.warpAffine(a.astype(np.float32), to, (w * s, h * s), flags=cv2.INTER_LANCZOS4), (0, 0), 2.8)
    return cv2.resize(np.clip((up - middle) / 0.16 + 0.5, 0, 1), (w, h), interpolation=cv2.INTER_AREA)


def main():
    titled, clean = key_visual("titled"), key_visual("clean")
    alpha = cut(titled, clean)
    logo = printed(alpha)
    small = line(SMALL, 0.46, 0.45)
    x, y = SMALL[0] * K // 2, SMALL[1] * K // 2
    part = logo[y:y + small.shape[0], x:x + small.shape[1]]
    np.maximum(part, small, out=part)
    subtitle = line(SUBTITLE, 0.5, 0.42)
    cv2.imwrite(str(SOURCES / "logo.png"), np.round(logo * 255).astype(np.uint8))
    cv2.imwrite(str(SOURCES / "logo-subtitle.png"), np.round(subtitle * 255).astype(np.uint8))
    cv2.imwrite(str(SOURCES / "logo-title.png"), title(titled, clean, alpha))
    print("logo", logo.shape[::-1], "subtitle", subtitle.shape[::-1])
    if "--check" in sys.argv:
        coarse = cv2.resize(cv2.imread(str(SOURCES / "logo-coarse.png"), cv2.IMREAD_GRAYSCALE), (W, H), interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(sys.argv[sys.argv.index("--check") + 1], np.vstack([coarse, np.round(logo * 255).astype(np.uint8)]))


if __name__ == "__main__":
    main()
