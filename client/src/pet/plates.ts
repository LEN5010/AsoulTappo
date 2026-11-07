// Name plates: a big hidden card worn under the pet on partners' desks, cut down to the strip
// across the eyes. The crops below are measured on the card art; `video` entries were measured
// frame by frame on the card video, which is framed differently from the still card.
import { getCard, manifest, type ManifestCard } from "../manifest";

/** A face on the card: eye centre (fx, fy) and face width (fw), all as fractions of the card. */
export interface PlateFace { fx: number; fy: number; fw: number }
export interface PlateCrop extends PlateFace {
  /** Replaces the still values for the card video. */
  video?: Partial<PlateFace>;
  /** Two faces the video strip glides between, for a card with two members one above the other. */
  pan?: readonly [Pick<PlateFace, "fx" | "fy">, Pick<PlateFace, "fx" | "fy">];
}

export const PLATE_CROPS: Readonly<Record<string, PlateCrop>> = {
  c1762331462002: { fx: 0.48, fy: 0.181, fw: 0.1, video: { fy: 0.2 } }, // 蝶影共醉
  c1781070981009: { fx: 0.48, fy: 0.25, fw: 0.13, video: { fy: 0.235 } }, // 珍馐派对
  c1700742793031: { fx: 0.49, fy: 0.291, fw: 0.11 }, // 时序系列-嘉然
  c1700742793032: { fx: 0.52, fy: 0.2755, fw: 0.1 }, // 时序系列-贝拉
  c1700742793033: { fx: 0.505, fy: 0.25, fw: 0.1 }, // 时序系列-乃琳
  c1745315724002: { fx: 0.475, fy: 0.287, fw: 0.12 }, // 绘心物语
  // 巡梦漫游: 心宜 in front, 思诺 above and behind her.
  c1748345610010: { fx: 0.42, fy: 0.232, fw: 0.13, pan: [{ fx: 0.415, fy: 0.245 }, { fx: 0.565, fy: 0.125 }] },
  c1756378523002: { fx: 0.34, fy: 0.355, fw: 0.11, video: { fy: 0.3 } }, // 时空行者
  c1787896765003: { fx: 0.47, fy: 0.208, fw: 0.1 }, // 歌剧之星
  c1785126321002: { fx: 0.48, fy: 0.167, fw: 0.15 }, // 月下童话
};

/** The eyes sit this far across the plate, below the character, who stands on the right of the pet. */
export const PLATE_ANCHOR = 0.7;
/** Face width over strip height: the strip shows the band from the brows to the nose. */
const FACE_SPAN = 1.7;
/** Card height over card width. */
const CARD_ASPECT = 1.5;

/** The card behind a plate id, if it is a big hidden card with a crop. */
export function plateCard(id: string | null | undefined): ManifestCard | null {
  const card = id ? getCard(id) : undefined;
  return card?.tier === "big" && PLATE_CROPS[card.id] ? card : null;
}

/** Every card that can be worn as a plate, in manifest order. */
export const plateCards = (): ManifestCard[] => manifest.cards.filter((c) => plateCard(c.id));

/** Plate size under a partner's pet drawn at `scale`. */
export function plateSize(scale: number): { width: number; height: number } {
  return { width: Math.max(120, Math.round(228 * scale)), height: Math.round(Math.min(40, Math.max(24, 30 * scale))) };
}

export interface ArtBox { width: number; height: number; left: number; top: number }

/** Where the card goes in a w x h strip: eyes at `anchor` across and mid-height, never past the card's edges. */
export function plateArt(face: PlateFace, w: number, h: number, anchor = PLATE_ANCHOR): ArtBox {
  const width = (FACE_SPAN * h) / face.fw;
  const height = width * CARD_ASPECT;
  const left = Math.min(0, Math.max(w - width, anchor * w - face.fx * width));
  const top = Math.min(0, Math.max(h - height, h / 2 - face.fy * height));
  return { width, height, left, top };
}

export const PAN_CYCLE_MS = 10000;
const HOLD_MS = 3500;
const GLIDE_MS = 1500;

/** 0 on the first face, 1 on the second: hold, glide, hold, glide back. */
export function panAt(ms: number): number {
  const t = ((ms % PAN_CYCLE_MS) + PAN_CYCLE_MS) % PAN_CYCLE_MS;
  const ease = (x: number) => (1 - Math.cos(Math.PI * x)) / 2;
  if (t < HOLD_MS) return 0;
  if (t < HOLD_MS + GLIDE_MS) return ease((t - HOLD_MS) / GLIDE_MS);
  if (t < 2 * HOLD_MS + GLIDE_MS) return 1;
  return 1 - ease((t - 2 * HOLD_MS - GLIDE_MS) / GLIDE_MS);
}

/** The face the video strip follows at time `ms`. */
export function videoFace(crop: PlateCrop, ms: number): PlateFace {
  const face = { fx: crop.fx, fy: crop.fy, fw: crop.fw, ...crop.video };
  if (!crop.pan) return face;
  const p = panAt(ms);
  const [a, b] = crop.pan;
  return { ...face, fx: a.fx + (b.fx - a.fx) * p, fy: a.fy + (b.fy - a.fy) * p };
}
