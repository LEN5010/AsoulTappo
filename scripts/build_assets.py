#!/usr/bin/env python3
"""Asset pipeline: raw 装扮/表情/卡牌 downloads -> compressed, de-duplicated,
manifest-described files in the repository.

    python scripts/build_assets.py --src /workspace/asoul-assets [--force]

Outputs
  client/public/assets/...        bundled in the desktop client, including card videos
  assets-packs/...                full card artwork and theme packs served by the room server
  assets-packs/manifest.json      canonical asset metadata (read by the server)
  assets-packs/index.json         pack list with per-file size + sha256
  client/src/data/manifest.json   copy of manifest.json used by the client build

Requires Pillow (WebP) and ffmpeg (libx264); card audio is copied from the source untouched.  Everything is selected from
scripts/asset_catalog.py (allowlists); unlisted source files are never touched.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asset_catalog as cat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "client" / "public" / "assets"
PACKS = ROOT / "assets-packs"
CLIENT_MANIFEST = ROOT / "client" / "src" / "data" / "manifest.json"

# compression recipe (see ASSETS.md)
EMOTE_PX = 320
CARD_FULL_W = 1080
CARD_THUMB = (414, 621)
THEME_BG_W = 720
THEME_BANNER_W = 720
THEME_HEAD_W = 828
THEME_TAB_W = 828
FRAME_PX = 240
FIGURE_PX = 200
ANIM_PX = 200
WEBP_Q = 82
ICON_Q = 90
THUMBUP_Q = 70
VIDEO_CRF = "28"
VIDEO_W = 640
VIDEO_FPS = 30
ICON_KEYS = ["main", "channel", "dynamic", "myself"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Ctx:
    def __init__(self, src: Path, force: bool):
        self.src = src
        self.force = force

    def todo(self, out: Path) -> bool:
        return self.force or not out.exists()


# ------------------------------------------------------------------ images
def resize_w(im: Image.Image, w: int) -> Image.Image:
    if im.width <= w:
        return im
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def save_webp(im: Image.Image, out: Path, q: int = WEBP_Q, lossless: bool = False) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
    im.save(out, "WEBP", quality=q, method=6, lossless=lossless, alpha_quality=100)


def load_rgba(path: Path | bytes) -> Image.Image:
    im = Image.open(io.BytesIO(path) if isinstance(path, bytes) else path)
    im.load()
    if im.mode == "P":
        im = im.convert("RGBA")
    return im


def square_fit(im: Image.Image, px: int) -> Image.Image:
    im = im.convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    scale = px / max(im.size)
    if scale < 1:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    return im


# ------------------------------------------------------------------ emotes
STEM_RE = re.compile(r"^(?P<stem>.*)-0_sticker_static\.png$")
BRACKET_RE = re.compile(r"^\[\s*[^\]_]*_(?P<n>.*)\]$")


def emote_name(stem: str) -> str:
    m = BRACKET_RE.match(stem)
    return (m.group("n") if m else stem).strip()


def has_hd(ctx: Ctx, dirname: str) -> bool:
    hd = ctx.src / "表情包" / dirname / "AI高清"
    return hd.is_dir() and any(STEM_RE.match(p.name) for p in hd.iterdir())


def emote_files(ctx: Ctx, dirname: str) -> list[tuple[str, Path]]:
    base = ctx.src / "表情包" / dirname
    folder = base / "AI高清" if has_hd(ctx, dirname) else base / "原图"
    out = []
    for p in sorted(folder.iterdir()):
        m = STEM_RE.match(p.name)
        if m:
            out.append((m.group("stem"), p))
    return out


def build_emotes(ctx: Ctx) -> list[dict]:
    sets: list[dict] = []
    seen: dict[str, str] = {}  # source sha -> output rel path (dedupe)

    def make_set(set_id, title, character, files, lossless):
        emotes = []
        for i, (stem, p) in enumerate(files, 1):
            rel = f"emotes/{set_id}/{i:02d}.webp"
            digest = sha256(p)
            if digest in seen:
                rel = seen[digest]
            else:
                seen[digest] = rel
                out = BUNDLE / rel
                if ctx.todo(out):
                    im = load_rgba(p)
                    im = square_fit(im, EMOTE_PX) if im.width > EMOTE_PX else im.convert("RGBA")
                    save_webp(im, out, q=85, lossless=lossless)
            emotes.append({"key": f"{set_id}.{i:02d}", "name": emote_name(stem), "img": f"bundle:{rel}"})
        sets.append({"id": set_id, "name": title, "character": character, "emotes": emotes})

    for set_id, title, character, dirname in cat.EMOTE_SETS:
        files = emote_files(ctx, dirname)
        make_set(set_id, title, character, files, not has_hd(ctx, dirname))
    for dirname, groups in cat.MIXED_EMOTE_SETS:
        files = {s: p for s, p in emote_files(ctx, dirname)}
        lossless = not has_hd(ctx, dirname)
        for set_id, title, character, stems in groups:
            make_set(set_id, title, character, [(s, files[s]) for s in stems], lossless)
    return sets


# ------------------------------------------------------ collection emotes
def build_collection_emotes(ctx: Ctx) -> list[dict]:
    sets = []
    for sid, title, member, album, folder in cat.COLLECTION_EMOTE_SETS:
        source = ctx.src / member / album / folder
        animated = folder == "动态表情包"
        suffix = "-0_sticker_gif.gif" if animated else "-0_sticker_static-AI高清.png"
        files = sorted(p for p in source.iterdir() if p.name.endswith(suffix))
        if not files:
            raise ValueError(f"No emotes in {source}")
        emotes = []
        for i, path in enumerate(files, 1):
            rel = f"emotes/{sid}/{i:02d}.webp"
            out = BUNDLE / rel
            if ctx.todo(out):
                with Image.open(path) as image:
                    if animated:
                        size = image.size
                        scale = min(1, EMOTE_PX / max(size))
                        target = tuple(max(1, round(n * scale)) for n in size)
                        frames, durations = [], []
                        for frame in ImageSequence.Iterator(image):
                            frames.append(frame.convert("RGBA").resize(target, Image.Resampling.LANCZOS))
                            durations.append(frame.info.get("duration", 100))
                        out.parent.mkdir(parents=True, exist_ok=True)
                        frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                                       duration=durations, loop=image.info.get("loop", 0), quality=85, method=6)
                    else:
                        save_webp(square_fit(image, EMOTE_PX), out, q=85)
            emotes.append({"key": f"{sid}.{i:02d}", "name": emote_name(path.name.removesuffix(suffix)),
                           "img": f"bundle:{rel}"})
        sets.append({"id": sid, "name": title, "character": member, "rarity": "common", "emotes": emotes})
    return sets


# ------------------------------------------------------------------- themes
def find_part(dirs: list[Path], prefix: str) -> Path | None:
    for d in dirs:
        for p in sorted(d.glob(prefix + "-0_other.*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bin"):
                return p
    return None


def find_backgrounds(dirs: list[Path], kind: str, limit: int) -> list[Path]:
    found: dict[int, Path] = {}
    for d in dirs:
        for p in d.glob(f"background_{kind}_*-0_other.*"):
            m = re.search(rf"background_{kind}_(\d+)-", p.name)
            if m:
                found.setdefault(int(m.group(1)), p)
    return [found[k] for k in sorted(found)][:limit]


def decode_bin_first_frame(p: Path) -> Image.Image | None:
    """`tail_icon_selected_*.bin` is a zlib'd container with PNG frames."""
    try:
        data = zlib.decompress(p.read_bytes())
    except zlib.error:
        return None
    sig = b"\x89PNG\r\n\x1a\n"
    i = data.find(sig)
    if i < 0:
        return None
    j = data.find(sig, i + 8)
    chunk = data[i : j if j > 0 else len(data)]
    try:
        im = Image.open(io.BytesIO(chunk))
        im.load()
        return im
    except Exception:
        return None


def apng_to_webp(src: Path, out: Path) -> None:
    im = Image.open(src)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        f = fr.convert("RGBA")
        f = f.resize((max(1, f.width // 2), max(1, f.height // 2)), Image.LANCZOS)
        frames.append(f)
        durations.append(fr.info.get("duration", im.info.get("duration", 33)) or 33)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, quality=THUMBUP_Q, method=4, alpha_quality=90)


def palette_from_cover(cover: Image.Image, fallback: str) -> dict:
    sm = cover.convert("RGB").resize((96, 128))
    q = sm.quantize(8, method=Image.MEDIANCUT)
    pal = q.getpalette()[:24]
    counts = sorted(q.getcolors(), reverse=True)
    best, best_score = None, -1.0
    for cnt, idx in counts:
        r, g, b = pal[idx * 3 : idx * 3 + 3]
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if not 0.32 < l < 0.72:
            continue
        score = s * (cnt ** 0.35)
        if score > best_score:
            best, best_score = (r, g, b), score
    accent = "#%02x%02x%02x" % best if best and best_score > 0.25 else fallback
    r, g, b = (int(accent[i : i + 2], 16) for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    tr, tg, tb = colorsys.hls_to_rgb(h, 0.94, min(s, 0.6))
    return {"accent": accent, "tint": "#%02x%02x%02x" % (round(tr * 255), round(tg * 255), round(tb * 255))}


def fg_for(im: Image.Image) -> str:
    """Readable text color (white or near-black) for the average luminance of an image."""
    raw = im.convert("RGBA").resize((32, 32)).tobytes()
    tot = n = 0.0
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i : i + 4]
        if a > 128:
            tot += 0.299 * r + 0.587 * g + 0.114 * b
            n += 1
    return "#ffffff" if n and tot / n < 140 else "#2b2020"


def build_themes(ctx: Ctx) -> list[dict]:
    themes = []
    for tid, title, chars, dirnames in cat.THEMES:
        is_default = tid == cat.DEFAULT_THEME
        dirs = [ctx.src / "主题" / d for d in dirnames if (ctx.src / "主题" / d).is_dir()]
        base = f"themes/{tid}"
        heavy_root, heavy_scheme = (BUNDLE, "bundle") if is_default else (PACKS, "pack")
        heavy_pack_files: list[str] = []

        def put_img(part: str, name: str, im: Image.Image, root: Path, scheme: str, q=WEBP_Q) -> str:
            rel = f"{base}/{name}.webp"
            out = root / rel
            if ctx.todo(out):
                save_webp(im, out, q=q)
            return f"{scheme}:{rel}"

        t: dict = {"id": tid, "name": title, "characters": chars, "default": is_default,
                   "pack": None if is_default else f"theme-{tid}", "parts": {}}
        # cover / preview (bundled)
        cover_p = find_part(dirs, "image_cover")
        cover_im = load_rgba(cover_p).convert("RGB")
        t["cover"] = put_img("cover", "cover", resize_w(cover_im, 300), BUNDLE, "bundle")
        prev_p = find_part(dirs, "image_preview")
        if prev_p:
            t["preview"] = put_img("preview", "preview", resize_w(load_rgba(prev_p).convert("RGB"), 300), BUNDLE, "bundle")
        t["colors"] = palette_from_cover(cover_im, cat.CHAR_BY_NAME[chars[0]]["color"])
        # tab icons (bundled)
        icons = {}
        for key in ICON_KEYS:
            n = find_part(dirs, f"tail_icon_{key}")
            if not n:
                continue
            ent = {"n": put_img("icon", f"icons/{key}", square_fit(load_rgba(n), 120), BUNDLE, "bundle", q=ICON_Q)}
            s = find_part(dirs, f"tail_icon_selected_{key}")
            sim = None
            if s:
                sim = decode_bin_first_frame(s) if s.suffix == ".bin" else load_rgba(s)
            if sim is not None:
                ent["s"] = put_img("icon", f"icons/{key}_sel", square_fit(sim, 120), BUNDLE, "bundle", q=ICON_Q)
            icons[key] = ent
        t["icons"] = icons
        # skin parts (default theme bundled, others in the theme pack)
        parts = t["parts"]
        p = find_part(dirs, "head_bg")
        if p:
            head_im = resize_w(load_rgba(p).convert("RGB"), THEME_HEAD_W)
            parts["headBg"] = put_img("head", "head_bg", head_im, heavy_root, heavy_scheme, q=80)
            t["colors"]["headFg"] = fg_for(head_im)
        p = find_part(dirs, "tail_bg")
        if p:
            tab_im = resize_w(load_rgba(p), THEME_TAB_W)
            parts["tabBg"] = put_img("tab", "tab_bg", tab_im, heavy_root, heavy_scheme, q=85)
            t["colors"]["tabFg"] = fg_for(tab_im)
        p = find_part(dirs, "head_myself_squared_bg")
        if p:
            parts["banner"] = put_img("banner", "banner", resize_w(load_rgba(p).convert("RGB"), THEME_BANNER_W), heavy_root, heavy_scheme, q=78)
        bgs = []
        for i, bp in enumerate(find_backgrounds(dirs, "portrait", 3), 1):
            bgs.append(put_img("bg", f"bg{i}", resize_w(load_rgba(bp).convert("RGB"), THEME_BG_W), heavy_root, heavy_scheme, q=78))
        if bgs:
            parts["backgrounds"] = bgs
        for d in dirs:
            tu = d / "thumbup" / "thumbup-0_thumbup.png"
            if tu.exists() and "thumbup" not in parts:
                rel = f"{base}/thumbup.webp"
                if ctx.todo(heavy_root / rel):
                    apng_to_webp(tu, heavy_root / rel)
                parts["thumbup"] = f"{heavy_scheme}:{rel}"
            ld = d / "loading" / "loading-0_loading.webp"
            if ld.exists() and "loading" not in parts:
                rel = f"{base}/loading.webp"
                (heavy_root / rel).parent.mkdir(parents=True, exist_ok=True)
                if ctx.todo(heavy_root / rel):
                    shutil.copyfile(ld, heavy_root / rel)
                parts["loading"] = f"{heavy_scheme}:{rel}"
        themes.append(t)
    return themes


# -------------------------------------------------------------------- cards
def find_card_files(ctx: Ctx, series: str, card_id: str) -> tuple[Path | None, Path | None]:
    d = ctx.src / "收藏集卡牌" / cat.CARD_SERIES[series][1]
    if not d.is_dir():
        d = ctx.src / cat.CARD_SOURCE_DIRS[series]
    img = vid = None
    for p in d.rglob(f"*-{card_id}_*"):
        if p.name.endswith("_card.png") or p.name.endswith("_card.jpg"):
            img = p
        elif p.name.endswith("_video.mp4"):
            vid = p
    return img, vid


def ffmpeg_video(src: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
           "-vf", f"scale={VIDEO_W}:-2:flags=lanczos,fps={VIDEO_FPS}",
           "-c:v", "libx264", "-crf", VIDEO_CRF, "-preset", "slow",
           "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-threads", "2", str(out)]
    subprocess.run(cmd, check=True)


def first_frame(src: Path) -> Image.Image:
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", "0.5", "-i", str(src), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], check=True, capture_output=True)
    return load_rgba(r.stdout)


def build_cards(ctx: Ctx, series_ids: set[str] | None = None) -> list[dict]:
    cards, video_jobs = [], []
    for series, card_id, name, chars in cat.CARDS:
        if series_ids is not None and series not in series_ids:
            continue
        img, vid = find_card_files(ctx, series, card_id)
        cid = f"c{card_id}"
        thumb_rel = f"cards/thumb/{cid}.webp"
        full_rel = f"cards/{series}/{cid}.webp"
        if img is None and vid is None:
            raise SystemExit(f"missing source for card {card_id} ({name})")
        need = ctx.todo(BUNDLE / thumb_rel) or ctx.todo(PACKS / full_rel)
        if need:
            im = load_rgba(img).convert("RGB") if img else first_frame(vid).convert("RGB")
            full = resize_w(im, CARD_FULL_W)
            save_webp(full, PACKS / full_rel, q=WEBP_Q)
            save_webp(im.resize(CARD_THUMB, Image.LANCZOS), BUNDLE / thumb_rel, q=80)
        card = {
            "id": cid, "name": name, "series": series,
            "sub": cat.card_subseries(series, name), "characters": chars,
            "rarity": cat.card_rarity(card_id, name, vid is not None),
            "tier": cat.card_tier(card_id),
            "thumb": f"bundle:{thumb_rel}", "full": f"pack:{full_rel}", "video": None,
        }
        if vid is not None:
            vrel = f"cards/{series}/{cid}.mp4"
            card["video"] = f"bundle:{vrel}"
            if ctx.todo(BUNDLE / vrel):
                video_jobs.append((vid, BUNDLE / vrel))
        cards.append(card)
    if video_jobs:
        print(f"encoding {len(video_jobs)} videos ...", flush=True)
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda j: ffmpeg_video(*j), video_jobs))
    return cards


def starter_items(emotes: list[dict]) -> dict:
    first_set: dict[str, dict] = {}
    for s in emotes:
        first_set.setdefault(s["character"], s)
    keys = [e["key"] for c in cat.CHARACTERS if c["name"] in first_set
            for e in first_set[c["name"]]["emotes"][: cat.STARTER_EMOTES]]
    return {"emotes": keys, "theme": cat.DEFAULT_THEME}


# ---------------------------------------------------------------- manifest
def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def collect_pack_files(manifest: dict) -> dict[str, list[str]]:
    packs: dict[str, list[str]] = {}
    for t in manifest["themes"]:
        if not t["pack"]:
            continue
        paths = []
        for v in t["parts"].values():
            for item in (v if isinstance(v, list) else [v]):
                scheme, rel = item.split(":", 1)
                assert scheme == "pack"
                paths.append(rel)
        packs[t["pack"]] = sorted(paths)
    for c in manifest["cards"]:
        packs.setdefault(f"cards-{c['series']}", []).append(c["full"].split(":", 1)[1])
    return {k: sorted(v) for k, v in packs.items()}


def build_index(manifest: dict) -> dict:
    out = []
    for pid, paths in sorted(collect_pack_files(manifest).items()):
        files = []
        for rel in paths:
            f = PACKS / rel
            files.append({"path": rel, "size": f.stat().st_size, "sha256": sha256(f)})
        title = pid
        if pid.startswith("theme-"):
            title = next(t["name"] for t in manifest["themes"] if t["pack"] == pid)
        elif pid.startswith("cards-"):
            title = cat.CARD_SERIES[pid[6:]][0] + " · 卡面"
        out.append({"id": pid, "title": title, "size": sum(x["size"] for x in files), "files": files})
    return {"version": 1, "packs": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/workspace/asoul-assets")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cards-only", action="store_true", help="Update cards while retaining existing themes and emotes")
    ap.add_argument("--emotes-only", action="store_true", help="Add collection emotes from the member/collection layout")
    ap.add_argument("--collection-src", help="Additional member/collection source when rebuilding all assets")
    ap.add_argument("--series", nargs="+", choices=cat.CARD_SERIES, help="Series to update with --cards-only")
    args = ap.parse_args()
    ctx = Ctx(Path(args.src), args.force)

    if args.emotes_only and args.cards_only:
        ap.error("--emotes-only and --cards-only are mutually exclusive")

    if args.series and not args.cards_only:
        ap.error("--series requires --cards-only")
    if args.cards_only or args.emotes_only:
        manifest = json.loads((PACKS / "manifest.json").read_text(encoding="utf-8"))
        selected = set(args.series or cat.CARD_SERIES)
        cards = ([c for c in manifest["cards"] if c["series"] not in selected] + build_cards(ctx, selected)
                 if args.cards_only else manifest["cards"])
        emotes, themes = manifest["emoteSets"], manifest["themes"]
        decor, accessories = manifest["decor"], manifest["accessories"]
    else:
        emotes = build_emotes(ctx)
        themes = build_themes(ctx)
        cards = build_cards(ctx)
        decor = []
        accessories = []
    if args.emotes_only or args.collection_src:
        additions = build_collection_emotes(Ctx(Path(args.collection_src or args.src), args.force))
        replaced = {s["id"] for s in additions}
        emotes = [s for s in emotes if s["id"] not in replaced] + additions
    elif not args.cards_only:
        previous = json.loads((PACKS / "manifest.json").read_text(encoding="utf-8"))
        collection_ids = {s[0] for s in cat.COLLECTION_EMOTE_SETS}
        emotes += [s for s in previous["emoteSets"] if s["id"] in collection_ids]
    for es in emotes:
        es["rarity"] = ("rare" if es["id"] in cat.RARE_EMOTE_SETS else
                        "uncommon" if es["id"] in cat.UNCOMMON_EMOTE_SETS else "common")
    for t in themes:
        t["rarity"] = None if t["default"] else cat.THEME_RARITY

    manifest = {
        "version": 4,
        "characters": cat.CHARACTERS,
        "rarities": {
            "common": {"name": "普通"},
            "uncommon": {"name": "罕见"},
            "rare": {"name": "稀有"},
            "epic": {"name": "史诗"},
            "legendary": {"name": "传说"},
        },
        "defaultTheme": cat.DEFAULT_THEME,
        "themes": themes,
        "series": [{"id": k, "name": v[0], "total": sum(1 for c in cards if c["series"] == k)}
                   for k, v in cat.CARD_SERIES.items()],
        "cards": cards,
        "emoteSets": emotes,
        "decor": decor,
        "accessories": accessories,
        "starter": starter_items(emotes),
        "skins": cat.SKINS,
        "economy": {"income": cat.INCOME, "resonance": cat.RESONANCE, "craftCost": cat.CRAFT_COST},
    }
    from build_previews import build_emote_covers, build_pet_previews
    build_emote_covers(manifest)
    build_pet_previews()
    write_json(PACKS / "manifest.json", manifest)
    write_json(CLIENT_MANIFEST, manifest)
    index = build_index(manifest)
    write_json(PACKS / "index.json", index)

    def tree_size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    biggest = max((f for r in (BUNDLE, PACKS) for f in r.rglob("*") if f.is_file()), key=lambda f: f.stat().st_size)
    print(f"bundled assets : {tree_size(BUNDLE) / 1e6:7.1f} MB")
    print(f"assets-packs   : {tree_size(PACKS) / 1e6:7.1f} MB")
    print(f"largest file   : {biggest.relative_to(ROOT)} {biggest.stat().st_size / 1e6:.1f} MB")
    print(f"{len(cards)} cards, {sum(len(s['emotes']) for s in emotes)} emotes, {len(themes)} themes, "
          f"{len(decor)} frames/badges, {len(accessories)} accessories")


if __name__ == "__main__":
    main()
