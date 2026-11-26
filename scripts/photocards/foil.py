"""Textures of the opening scene: the room the film mirrors, a soft shadow.
   usage: foil.py <working directory>"""
import sys
from pathlib import Path
import numpy as np, cv2

ROOT = Path(sys.argv[1])
OUT = ROOT / "open" / "tex"
rng = np.random.default_rng(20261125)

step = lambda a, b, t: (lambda k: k * k * (3 - 2 * k))(np.clip((t - a) / (b - a), 0, 1))

# The room mirrored in the film, in stereographic coordinates of the reflected ray: the middle lies behind the viewer.
# The film is flat, so it mirrors only a small part at a time: tall lit panes with dark between, all the way across.
N = 512
ex, ey = np.meshgrid((np.arange(N) + 0.5) / N * 2 - 1, (np.arange(N) + 0.5) / N * 2 - 1)
x = ex + 0.16 * ey
stops = [(-1.6, .14), (-.82, .12), (-.70, .30), (-.60, .86), (-.50, .94), (-.45, .52), (-.42, .20), (-.33, .16), (-.25, .40), (-.215, .82), (-.13, .96), (-.085, .80),
         (-.065, .40), (-.03, .30), (.03, .44), (.055, .74), (.12, .90), (.17, .70), (.19, .34), (.25, .24), (.33, .42), (.36, .84), (.45, .95), (.52, .60), (.55, .24), (.66, .14),
         (.74, .44), (.80, .80), (.88, .40), (1.0, .12), (1.6, .12)]
level = np.interp(x, [a for a, _ in stops], [b for _, b in stops])
down, up = step(.30, .85, ey), step(.35, .9, -ey)
level = level * (1 - .62 * down)
level = level * (1 - .6 * up) + .93 * .6 * up
level = cv2.GaussianBlur(level.astype(np.float32), (0, 0), 1.1)
room = level[..., None] * np.array([1.0, 1.0, 1.015]) + (1 - level[..., None]) * np.array([.012, .014, .032])
cv2.imwrite(str(OUT / "room.png"), np.clip(room[..., ::-1] * 240, 0, 255).astype(np.uint8))

# A soft rounded-rectangle shadow.
S = 256
sxx, syy = np.meshgrid((np.arange(S) + 0.5) / S * 2 - 1, (np.arange(S) + 0.5) / S * 2 - 1)
dxy = np.stack([np.abs(sxx) - 0.62 + 0.08, np.abs(syy) - 0.62 + 0.08], -1)
dist = np.linalg.norm(np.maximum(dxy, 0), axis=-1) + np.minimum(dxy.max(-1), 0) - 0.08
shadow = cv2.GaussianBlur((dist < 0).astype(np.float32), (0, 0), 22)
cv2.imwrite(str(OUT / "shadow.png"), np.clip(shadow * 255, 0, 255).astype(np.uint8))
print("done")
