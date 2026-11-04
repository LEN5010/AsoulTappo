#!/usr/bin/env python3
"""Generate the panel's display font subset and halftone pattern.

Usage:
    python scripts/build_ui_assets.py --smiley <SmileySans-Oblique.ttf>

The font step needs `pip install fonttools brotli`. Re-run it after adding UI text:
characters missing from the subset fall back to the system font, one glyph at a time.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
FONT_OUT = CLIENT / "src/assets/fonts/SmileySans-subset.woff2"
HALFTONE_OUT = CLIENT / "src/assets/patterns/halftone.svg"

CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")


def ui_text() -> str:
    """Printable ASCII, every CJK character in the client source, and catalog titles."""
    chars = {chr(c) for c in range(0x20, 0x7f)}
    for path in (CLIENT / "src").rglob("*"):
        if path.suffix in {".vue", ".ts"} and not path.name.endswith(".test.ts"):
            chars.update(CJK.findall(path.read_text(encoding="utf-8")))
    manifest = json.loads((CLIENT / "src/data/manifest.json").read_text(encoding="utf-8"))
    for group in ("characters", "series", "emoteSets"):
        for entry in manifest[group]:
            chars.update(CJK.findall(entry["name"]))
    return "".join(sorted(chars))


def subset_font(src: Path) -> None:
    FONT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as text:
        text.write(ui_text())
        text.flush()
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset", str(src),
                f"--text-file={text.name}", f"--output-file={FONT_OUT}",
                "--flavor=woff2", "--layout-features=*",
            ],
            check=True,
        )
    print(f"{FONT_OUT.relative_to(ROOT)}: {FONT_OUT.stat().st_size / 1024:.0f} KB")


def halftone(cols: int = 28, rows: int = 24, pitch: float = 10.0, max_r: float = 4.6) -> None:
    """Staggered dots growing toward the bottom edge; used as a CSS mask, so any color works."""
    HALFTONE_OUT.parent.mkdir(parents=True, exist_ok=True)
    width, height = cols * pitch, rows * pitch
    parts = []
    for row in range(rows):
        radius = round(max_r * ((row + 1) / rows) ** 1.5, 2)
        if radius < 0.25:
            continue
        y = (row + 0.5) * pitch
        offset = pitch / 2 if row % 2 else 0
        for col in range(cols + 1):
            x = col * pitch + offset
            parts.append(f"M{x - radius:g} {y:g}a{radius:g} {radius:g} 0 1 0 {radius * 2:g} 0a{radius:g} {radius:g} 0 1 0 {-radius * 2:g} 0")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        f'width="{width:g}" height="{height:g}"><path d="{"".join(parts)}"/></svg>\n'
    )
    HALFTONE_OUT.write_text(svg, encoding="utf-8")
    print(f"{HALFTONE_OUT.relative_to(ROOT)}: {len(svg) / 1024:.0f} KB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smiley", type=Path, help="path to SmileySans-Oblique.ttf; omit to skip the font step")
    args = parser.parse_args()
    if args.smiley:
        subset_font(args.smiley)
    halftone()


if __name__ == "__main__":
    main()
