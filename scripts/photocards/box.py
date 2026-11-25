"""The box's printed faces: coverage of the white lettering, into open/tex/. usage: box.py <working directory> <asoul-logo png>"""
import sys
from pathlib import Path
import numpy as np, cv2
ROOT = Path(sys.argv[1]); OUT = ROOT / "open" / "tex"
def mask(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im.ndim == 2: return im
    return im[..., 3] if im.shape[2] == 4 else cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
def put(dst, m, cx, cy, w):
    h = int(round(w * m.shape[0] / m.shape[1]))
    r = cv2.resize(m, (int(w), h), interpolation=cv2.INTER_AREA if w < m.shape[1] else cv2.INTER_CUBIC)
    x, y = int(round(cx - r.shape[1] / 2)), int(round(cy - h / 2))
    dst[y:y + h, x:x + r.shape[1]] = np.maximum(dst[y:y + h, x:x + r.shape[1]], r)
# Measured on the photographs: the face is 860 x 1165 of them. The atlas is 1280 x 1024 units of FINE px.
FINE = 2
FW, FH = 755 * FINE, 1024 * FINE
front = np.zeros((FH, FW), np.uint8)
logo, sub = mask(ROOT / "src/logo.png"), mask(ROOT / "src/logo-subtitle.png")
print(logo.shape, logo.max(), sub.shape, sub.max())
k = FW / 860
put(front, logo, (660 - 232) * k, (1142 - 585) * k, 636 * k)
put(front, sub, (661 - 232) * k, (1254 - 585) * k, 424 * k)
SW, SH = 400 * FINE, 1024 * FINE
side = np.zeros((SH, SW), np.uint8)
a = mask(Path(sys.argv[2]))
a = cv2.rotate(a, cv2.ROTATE_90_COUNTERCLOCKWISE)
w = int(128 / 450 * SW)
put(side, a, (736 - 515) / 450 * SW, (1090 - 545) / 1105 * SH, w)
atlas = np.zeros((1024 * FINE, 1280 * FINE), np.uint8)
atlas[:FH, :FW] = front
atlas[:SH, 780 * FINE:780 * FINE + SW] = side
cv2.imwrite(str(OUT / "box-print.png"), atlas)
