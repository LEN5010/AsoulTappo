// Name plates worn under the pet on partners' desks. Three kinds:
// - a big hidden card, worn under its card id, cut down to the strip across the eyes. The crops below are measured
//   on the card art; `video` entries were measured frame by frame on the card video, which is framed differently.
// - a plate listed in the manifest (`plates`), unlocked by a whole emote set: a still picture that sweeps between
//   two bands of it (PLATE_SWEEPS).
// - a plate listed in the manifest with a card `series` (衣橱), unlocked by the whole series: its own video, cut
//   with one fixed crop like a big hidden card's (PLATE_MOTIONS).
import alpaca from "../assets/brand/side-alpaca.webp";
import { getCard, manifest, type ManifestCard, type ManifestEmote, type ManifestPlate } from "../manifest";

/** A face on the card: eye centre (fx, fy) and face width (fw), all as fractions of the card. */
export interface PlateFace { fx: number; fy: number; fw: number }
export interface PlateCrop extends PlateFace {
  /** Replaces the still values for the card video. */
  video?: Partial<PlateFace>;
  /** Two faces the video strip glides between, for a card with two members one above the other. */
  pan?: readonly [Pick<PlateFace, "fx" | "fy">, Pick<PlateFace, "fx" | "fy">];
  /** Where the profile banner centres instead of the eyes, as a fraction of the card's height. */
  bannerFy?: number;
}

export const PLATE_CROPS: Readonly<Record<string, PlateCrop>> = {
  c1762331462002: { fx: 0.48, fy: 0.181, fw: 0.1, video: { fy: 0.2 } }, // 蝶影共醉
  c1781070981009: { fx: 0.48, fy: 0.25, fw: 0.13, video: { fy: 0.235 } }, // 珍馐派对
  c1700742793031: { fx: 0.49, fy: 0.291, fw: 0.11 }, // 时序系列-嘉然
  c1700742793032: { fx: 0.52, fy: 0.2755, fw: 0.1 }, // 时序系列-贝拉
  c1700742793033: { fx: 0.505, fy: 0.25, fw: 0.1 }, // 时序系列-乃琳
  c1745315724002: { fx: 0.475, fy: 0.287, fw: 0.12 }, // 绘心物语
  // 巡梦漫游: 心宜 in front, 思诺 above and behind her.
  c1748345610010: {
    fx: 0.42, fy: 0.232, fw: 0.13, pan: [{ fx: 0.415, fy: 0.245 }, { fx: 0.565, fy: 0.125 }], bannerFy: 0.2,
  },
  c1756378523002: { fx: 0.34, fy: 0.355, fw: 0.11, video: { fy: 0.3 } }, // 时空行者
  c1787896765003: { fx: 0.47, fy: 0.208, fw: 0.1 }, // 歌剧之星
  c1785126321002: { fx: 0.48, fy: 0.167, fw: 0.15 }, // 月下童话
};

/** A pan between two bands (ms): rest on the first, glide to the second, rest there, glide back. */
export interface PanRhythm { first: number; toSecond: number; second: number; toFirst: number }
/** Card videos with two faces: equal rests and glides. */
export const CARD_PAN: PanRhythm = { first: 3500, toSecond: 1500, second: 3500, toFirst: 1500 };
export const panCycle = (r: PanRhythm) => r.first + r.toSecond + r.second + r.toFirst;
export const PAN_CYCLE_MS = panCycle(CARD_PAN);

// 阿草's plate rests on the crossed arms, sweeps slowly up past the bow tie, rests on the face, and drops back.
export const ACHAO_ARMS_MS = 800;
export const ACHAO_RISE_MS = 4500;
export const ACHAO_FACE_MS = 6000;
export const ACHAO_FALL_MS = 1200;

/** A still picture worn as a plate: it rests on `from`, sweeps to `face` and back. A still plate shows `face`. */
export interface PlateSweep {
  src: string;
  /** Picture height over width. */
  aspect: number;
  face: PlateFace;
  from: Pick<PlateFace, "fx" | "fy">;
  rhythm: PanRhythm;
}

export const PLATE_SWEEPS: Readonly<Record<string, PlateSweep>> = {
  // The sidebar alpaca, 420 x 620 on a transparent ground: eyes, nose and smile; the crossed arms; the bow tie at
  // fy 0.53 on the way, whole in the strip. The cut-out is narrower than the strip on purpose: coral shows at the
  // left, under the nickname, and the face sits clear of it at the anchor.
  achao: {
    src: alpaca,
    aspect: 620 / 420,
    face: { fx: 0.49, fy: 0.21, fw: 0.34 },
    from: { fx: 0.49, fy: 0.7 },
    rhythm: { first: ACHAO_ARMS_MS, toSecond: ACHAO_RISE_MS, second: ACHAO_FACE_MS, toFirst: ACHAO_FALL_MS },
  },
};

/**
 * A series plate's video under one fixed crop: the face as fractions of the video frame, at the middle of where the
 * eyes go over the loop, drawn a little smaller than a tight crop so more of the face shows. `gap` is how much of the
 * strip's width the video may leave bare at the left, under the nickname, to bring a face that sits left in its video
 * over to the anchor.
 */
export interface PlateMotion { face: PlateFace; gap?: number }

export const PLATE_MOTIONS: Readonly<Record<string, PlateMotion>> = {
  "wardrobe-jiaran": { face: { fx: 0.646, fy: 0.34, fw: 0.146 } }, // 嘉然个性装扮 2.0, dark theme
  "wardrobe-nailin": { face: { fx: 0.655, fy: 0.358, fw: 0.195 } }, // 乃琳个性装扮 2.0, light theme
  "wardrobe-beila": { face: { fx: 0.471, fy: 0.42, fw: 0.18 }, gap: 0.2 }, // 贝拉个性装扮 2.0, light theme
};

type SeriesPlate = Extract<ManifestPlate, { series: string }>;

export type Plate =
  | { kind: "card"; id: string; name: string; card: ManifestCard; crop: PlateCrop }
  /** `set` is the emote set that unlocks it. */
  | { kind: "sweep"; id: string; name: string; set: string; emotes: ManifestEmote[]; sweep: PlateSweep }
  /** `cards` is the series that unlocks it; `video`, `poster` and `still` are asset references. */
  | {
    kind: "series"; id: string; name: string; series: string; cards: ManifestCard[];
    video: string; poster: string; still: string; aspect: number; motion: PlateMotion;
  };

const TIER_ORDER = { big: 0, small: 1, normal: 2 } as const;

/** Every plate: big hidden cards in manifest order, then the manifest's plates. */
const PLATES: readonly Plate[] = [
  ...manifest.cards.flatMap((card): Plate[] => {
    const crop = PLATE_CROPS[card.id];
    return card.tier === "big" && crop ? [{ kind: "card", id: card.id, name: card.name, card, crop }] : [];
  }),
  ...manifest.plates.flatMap((p): Plate[] => {
    if (getCard(p.id)) return [];
    if (p.series !== undefined) return seriesPlate(p);
    const sweep = PLATE_SWEEPS[p.id];
    const emotes = manifest.emoteSets.find((s) => s.id === p.emoteSet)?.emotes ?? [];
    return sweep && emotes.length ? [{ kind: "sweep", id: p.id, name: p.name, set: p.emoteSet, emotes, sweep }] : [];
  }),
];

function seriesPlate(p: SeriesPlate): Plate[] {
  const motion = PLATE_MOTIONS[p.id];
  const cards = manifest.cards.filter((c) => c.series === p.series);
  return motion && cards.length ? [{
    kind: "series", id: p.id, name: p.name, series: p.series, cards,
    video: p.video, poster: p.poster, still: p.still, aspect: p.aspect, motion,
  }] : [];
}
const plateIndex = new Map(PLATES.map((p) => [p.id, p]));

export const allPlates = (): readonly Plate[] => PLATES;

/** The plate behind a plate id: a big hidden card with a crop, or a manifest plate with its picture. */
export function getPlate(id: string | null | undefined): Plate | null {
  return (id && plateIndex.get(id)) || null;
}

/** The members a plate shows. */
export function plateMembers(plate: Plate): string[] {
  if (plate.kind === "card") return plate.card.characters;
  if (plate.kind === "series") return [...new Set(plate.cards.flatMap((c) => c.characters))];
  return [];
}

/** The card behind a plate id, if it is a big hidden card with a crop. */
export function plateCard(id: string | null | undefined): ManifestCard | null {
  const plate = getPlate(id);
  return plate?.kind === "card" ? plate.card : null;
}

/**
 * Cards a plate asks for, its big hidden card first: those of its collection that show one of its members.
 * A collection of several members asks only for the plate member's cards; a duo card asks for the whole
 * duo collection. Same rule as the server (game.py plate_set).
 */
export function plateSet(card: ManifestCard): ManifestCard[] {
  return manifest.cards
    .filter((c) => c.series === card.series && c.characters.some((m) => card.characters.includes(m)))
    .sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier]);
}

/** The cards a plate asks for: a big hidden card's set, or a series plate's series; none for an emote plate. */
export function plateCards(plate: Plate): ManifestCard[] {
  if (plate.kind === "card") return plateSet(plate.card);
  return plate.kind === "series" ? plate.cards : [];
}

/** Item ids a plate asks for: its cards, or every emote of its set. Same rule as the server (game.py plate_needs). */
export function plateNeeds(plate: Plate): string[] {
  return plate.kind === "sweep" ? plate.emotes.map((e) => `emote:${e.key}`) : plateCards(plate).map((c) => `card:${c.id}`);
}

/** A plate is worn once its whole set is collected. */
export function plateUnlocked(id: string | null | undefined, owned: Readonly<Record<string, number>>): boolean {
  const plate = getPlate(id);
  return !!plate && plateNeeds(plate).every((item) => owned[item]);
}

/** Plate size under a partner's pet drawn at `scale`. */
export function plateSize(scale: number): { width: number; height: number } {
  return { width: Math.round(228 * scale), height: Math.round(Math.min(40, Math.max(16, 30 * scale))) };
}

/** Partner scale down to which the nickname keeps its full size; smaller partners shrink it. */
const FULL_NAME_SCALE = 0.8;

/** Nickname font size and plain name tag height (px) under a partner's pet drawn at `scale`. */
export function nameBand(scale: number): { font: number; pill: number } {
  const k = Math.min(1, scale / FULL_NAME_SCALE);
  // 12px is --fs-label, 22px the tag's own height.
  return { font: Math.round(Math.max(10, 12 * k)), pill: Math.round(Math.max(16, 22 * k)) };
}

/** The eyes sit this far across the plate, below the character, who stands on the right of the pet. */
export const PLATE_ANCHOR = 0.7;
/** Face width over strip height: the strip shows the band from the brows to the nose. */
const FACE_SPAN = 1.7;
/** Card height over card width. */
export const CARD_ASPECT = 1.5;

export interface ArtBox { width: number; height: number; left: number; top: number }

/**
 * `at`, moved as little as needed so art larger than the strip covers it and art smaller stays whole inside it.
 * `room` lets art larger than the strip start that far in from the strip's start, leaving a bare edge.
 */
const within = (at: number, slack: number, room = 0) =>
  Math.min(Math.max(at, Math.min(0, slack)), Math.max(room, slack));

/** How large the face is drawn: `span` is face width over the frame's height. */
export interface ArtFit { span: number }
/** The plate under a pet: the band from the brows to the nose. */
export const STRIP_FIT: ArtFit = { span: FACE_SPAN };
/** A sweep plate on a profile namecard: its cut-out with more around the face, still standing on its coral. */
export const BANNER_FIT: ArtFit = { span: 0.45 };
/** A namecard's artwork spans at most this many times its height, the framing the banner crops are set for. */
export const BANNER_ASPECT = 3;
/** On the banner the eyes sit this far down, a little above the middle, leaving room for the shoulders. */
export const BANNER_EYES = 0.45;

/**
 * Where the picture (height `aspect` x its width) goes in a w x h strip: eyes at `anchor` across and mid-height,
 * never past the picture's edges where it is larger than the strip, never cut where it is smaller. `gap` (a share of
 * the strip's width) lets the picture start that far in from the left, bare strip showing there.
 */
export function plateArt(
  face: PlateFace, w: number, h: number, anchor = PLATE_ANCHOR, aspect = CARD_ASPECT, fit: ArtFit = STRIP_FIT, gap = 0,
): ArtBox {
  const width = (fit.span * h) / face.fw;
  const height = width * aspect;
  return {
    width, height,
    left: within(anchor * w - face.fx * width, w - width, gap * w),
    top: within(h / 2 - face.fy * height, h - height),
  };
}

/** Where a series plate's video (and its poster) goes in a w x h strip. On a long strip (a large pet) the video is drawn
 * larger, at least as wide as the strip, so it never leaves the right of the strip bare. */
export function motionArt(plate: Extract<Plate, { kind: "series" }>, w: number, h: number): ArtBox {
  const { face, gap = 0 } = plate.motion;
  const fit = { span: Math.max(FACE_SPAN, (w * face.fw) / h) };
  return plateArt(face, w, h, PLATE_ANCHOR, plate.aspect, fit, gap);
}

/**
 * Where a card goes on a profile namecard: the full-size still exactly as wide as the artwork, so it is drawn at about
 * its own resolution (the video is too small for a banner), the eyes BANNER_EYES down. A wide picture on a narrow
 * banner is drawn as tall as the banner instead, overflowing at the right.
 */
export function bannerArt(crop: PlateCrop, w: number, h: number, aspect = CARD_ASPECT): ArtBox {
  const width = Math.max(w, h / aspect);
  const height = width * aspect;
  return { width, height, left: 0, top: within(BANNER_EYES * h - (crop.bannerFy ?? crop.fy) * height, h - height) };
}

/** Where a sweep plate's picture goes on its face and on its first band. */
export function sweepArt(sweep: PlateSweep, w: number, h: number, fit: ArtFit = STRIP_FIT): { face: ArtBox; from: ArtBox } {
  return {
    face: plateArt(sweep.face, w, h, PLATE_ANCHOR, sweep.aspect, fit),
    from: plateArt({ ...sweep.face, ...sweep.from }, w, h, PLATE_ANCHOR, sweep.aspect, fit),
  };
}

const glide = (x: number) => (1 - Math.cos(Math.PI * x)) / 2;
/** CSS easing close to `glide`. */
export const GLIDE_EASING = "cubic-bezier(0.37, 0, 0.63, 1)";

/** 0 on the first band, 1 on the second: rest, glide, rest, glide back. */
export function panAt(ms: number, r: PanRhythm = CARD_PAN): number {
  const cycle = panCycle(r);
  const t = ((ms % cycle) + cycle) % cycle;
  if (t < r.first) return 0;
  if (t < r.first + r.toSecond) return glide((t - r.first) / r.toSecond);
  if (t < r.first + r.toSecond + r.second) return 1;
  return 1 - glide((t - r.first - r.toSecond - r.second) / r.toFirst);
}

/** panAt's cycle as Web Animations keyframe stops: `p` as panAt has it at `offset` of the cycle. */
export function sweepFrames(r: PanRhythm): { offset: number; p: number; easing: string }[] {
  const cycle = panCycle(r);
  return [
    { offset: 0, p: 0, easing: "linear" },
    { offset: r.first / cycle, p: 0, easing: GLIDE_EASING },
    { offset: (r.first + r.toSecond) / cycle, p: 1, easing: "linear" },
    { offset: (r.first + r.toSecond + r.second) / cycle, p: 1, easing: GLIDE_EASING },
    { offset: 1, p: 0, easing: "linear" },
  ];
}

/** The face the video strip follows at time `ms`. */
export function videoFace(crop: PlateCrop, ms: number): PlateFace {
  const face = { fx: crop.fx, fy: crop.fy, fw: crop.fw, ...crop.video };
  if (!crop.pan) return face;
  const p = panAt(ms);
  const [a, b] = crop.pan;
  return { ...face, fx: a.fx + (b.fx - a.fx) * p, fy: a.fy + (b.fy - a.fy) * p };
}
