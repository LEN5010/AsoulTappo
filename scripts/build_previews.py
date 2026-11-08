#!/usr/bin/env python3
"""Generate static emote covers and size-specific pet images from bundled originals.

Run after replacing pet artwork or rebuilding the asset catalog:
    server/.venv/bin/python scripts/build_previews.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "client/public/assets"
CHARACTERS = ROOT / "client/src/assets/characters"
PREVIEWS = ROOT / "client/src/assets/previews/characters"


def save(im: Image.Image, out: Path, size: tuple[int, int]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    im = im.convert("RGBA")
    im.thumbnail(size, Image.Resampling.LANCZOS)
    im.save(out, "WEBP", quality=86, method=6)


def build_emote_covers(manifest: dict) -> int:
    count = 0
    for group in manifest["emoteSets"]:
        for emote in group["emotes"]:
            source = BUNDLE / emote["img"].removeprefix("bundle:")
            with Image.open(source) as im:
                if getattr(im, "is_animated", False):
                    out = source.with_name(source.stem + "-cover.webp")
                    save(im, out, (160, 160))
                    emote["thumb"] = "bundle:" + out.relative_to(BUNDLE).as_posix()
                    emote["animated"] = True
                    count += 1
                else:
                    emote.pop("thumb", None)
                    emote.pop("animated", None)
    return count


def build_pet_previews() -> int:
    count = 0
    for source in sorted(CHARACTERS.glob("*/bgImage.webp")):
        out = PREVIEWS / source.parent.name
        with Image.open(source) as im:
            save(im, out / "bg-480.webp", (480, 270))
            save(im, out / "bg-960.webp", (960, 540))
            # Same crop as FACE_CROP in characters.ts, measured on a 240x135 canvas.
            crop = im.crop((round(im.width * 90 / 240), 0,
                            round(im.width * 222 / 240), round(im.height * 112 / 135)))
            save(crop, out / "face.webp", (264, 224))
        count += 1
    return count


def main() -> None:
    manifest_path = ROOT / "assets-packs/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    covers = build_emote_covers(manifest)
    for path in (manifest_path, ROOT / "client/src/data/manifest.json"):
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    pets = build_pet_previews()
    print(f"Generated {covers} static emote covers and previews for {pets} pets")


if __name__ == "__main__":
    main()
