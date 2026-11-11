#!/usr/bin/env python3
"""Generate the panel's bundled fonts and halftone pattern.

Usage:
    python scripts/build_ui_assets.py --noto <NotoSansSC[wght].ttf>

The font step needs `pip install fonttools brotli`. Re-run it after adding UI text:
characters missing from the subsets fall back to the system font, one glyph at a time.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
TEXT_OUT = CLIENT / "src/assets/fonts/NotoSansSC-subset.woff2"
HALFTONE_OUT = CLIENT / "src/assets/patterns/halftone.svg"

NON_ASCII = re.compile(r"[^\x00-\x7f]")
TEXT_WEIGHTS = (400, 400, 800)


def ui_text() -> str:
    """Printable ASCII plus every non-ASCII character in the client source and catalog, and in the server
    source, whose refusal messages the client shows as they come."""
    chars = {chr(c) for c in range(0x20, 0x7f)}
    for path in (CLIENT / "src").rglob("*"):
        if path.suffix in {".vue", ".ts", ".json", ".md"} and not path.name.endswith(".test.ts"):
            chars.update(NON_ASCII.findall(path.read_text(encoding="utf-8")))
    for path in (ROOT / "server" / "app").rglob("*.py"):
        chars.update(NON_ASCII.findall(path.read_text(encoding="utf-8")))
    return "".join(sorted(chars))


def load_subset(src: Path, text: str):
    from fontTools.subset import Options, Subsetter
    from fontTools.ttLib import TTFont

    font = TTFont(src)
    subsetter = Subsetter(Options(hinting=False))
    subsetter.populate(text=text)
    subsetter.subset(font)
    return font


def write_font(font, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(out)
    print(f"{out.relative_to(ROOT)}: {out.stat().st_size / 1024:.0f} KB")


def build_fonts(src: Path) -> None:
    from fontTools.varLib.instancer import instantiateVariableFont

    text = ui_text()
    write_font(instantiateVariableFont(load_subset(src, text), {"wght": TEXT_WEIGHTS}), TEXT_OUT)


def halftone(cols: int = 20, rows: int = 10, pitch: float = 14.0, max_r: float = 2.4) -> None:
    """Sparse staggered dots growing toward the bottom edge; used as a CSS mask, so any color works.

    Keep the gaps around three dot diameters: tight clusters of round dots read as trypophobic.
    """
    HALFTONE_OUT.parent.mkdir(parents=True, exist_ok=True)
    width, height = cols * pitch, rows * pitch
    parts = []
    for row in range(rows):
        radius = round(max_r * ((row + 1) / rows) ** 1.2, 2)
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
    parser.add_argument("--noto", type=Path, help="path to the NotoSansSC[wght].ttf variable font; omit to skip the font step")
    args = parser.parse_args()
    if args.noto:
        build_fonts(args.noto)
    halftone()


if __name__ == "__main__":
    main()
