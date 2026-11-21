// The first-run guide: four steps on the desk, each circling one place on the strip under the pet with a line of
// text. Progress lives in the settings (`guide`), shared by the desk and the panel window; this file decides which
// card is due from that progress and from what the desk reports now. Each card shows once and has no skip: the player
// answers every one. The standalone edition has no resonance, so its guide has no draw card.

import { STANDALONE } from "./edition";

/** Raised when the guide is to be shown to everyone again. 1: from 1.2.6, to new and old players alike. */
export const GUIDE_V = 1;

export interface Guide {
  /** GUIDE_V of the run that started it; 0 = never started. */
  v: number;
  /** The cards answered: closed, or their place used. */
  done: string[];
}

export const CARDS = ["tap", "draw", "panel", "grip"] as const;
export type Card = (typeof CARDS)[number];
/** The cards of this edition. */
const STEPS: readonly Card[] = STANDALONE ? CARDS.filter((c) => c !== "draw") : CARDS;

/** The line on each card: one line, twelve characters at most. */
export const GUIDE_TEXT: Record<Card, string> = {
  tap: "按键和点击会计入敲击",
  draw: "碎片足够后从这里开始共鸣",
  panel: "从这个按钮打开面板",
  grip: "收起任务栏和番茄钟的入口",
};

/** The `data-guide` name of the place each card circles. */
export const GUIDE_TARGET: Record<Card, string> = {
  tap: "count",
  draw: "draw",
  panel: "menu",
  grip: "grip",
};

const isCard = (s: unknown): s is Card => typeof s === "string" && (CARDS as readonly string[]).includes(s);

/** The stored guide, or a guide never started for anything else; always a fresh object. */
export function cleanGuide(raw: unknown): Guide {
  const g = (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {}) as Partial<Guide>;
  const v = typeof g.v === "number" && Number.isFinite(g.v) && g.v >= 0 ? Math.floor(g.v) : 0;
  return { v, done: Array.isArray(g.done) ? [...new Set(g.done.filter(isCard))] : [] };
}

/** Whether this guide is to start (again): never started, or started by an older GUIDE_V. */
export const guideDue = (g: Guide): boolean => g.v < GUIDE_V;
export const startGuide = (): Guide => ({ v: GUIDE_V, done: [] });
export const withDone = (g: Guide, card: Card): Guide =>
  (g.done.includes(card) ? g : { ...g, done: [...g.done, card] });
/** Some cards are not answered yet. */
export const guideLeft = (g: Guide): boolean => STEPS.some((c) => !g.done.includes(c));

/**
 * The progress after [incoming] from another window meets [local]: what either window answered stays answered, so a
 * message sent before a later change never undoes it. A guide started again for a newer GUIDE_V replaces the older one
 * as a whole.
 */
export function mergeGuide(local: Guide, incoming: Guide): Guide {
  if (incoming.v !== local.v) return cleanGuide(incoming.v > local.v ? incoming : local);
  return { v: local.v, done: [...new Set([...local.done, ...incoming.done])] };
}

/** What the desk window knows now. */
export interface DeskFacts {
  agreed: boolean;
  /** Something with a better claim is over the pet (a permission, admin or auto-input note, a cooldown, an invite, a reminder). */
  busy: boolean;
  /**
   * The panel is still going through what it opens with (terms, update, announcements, new skins, rewards, a reveal),
   * as it last said; also while it is hidden. False when no panel came up this run.
   */
  panelBusy: boolean;
  /** The panel is on screen. */
  panelVisible: boolean;
  /** An input was counted since the terms were agreed to, this run. */
  tapped: boolean;
  /** The `data-guide` places drawn in this window now. */
  targets: ReadonlySet<string>;
}

/** The card the desk wants up now, or null. */
export function deskCard(g: Guide, f: DeskFacts): Card | null {
  if (guideDue(g) || !f.agreed || f.busy || f.panelBusy) return null;
  const done = (c: Card) => g.done.includes(c);
  const has = (t: string) => f.targets.has(t);
  // A step whose place is not drawn (a folded strip, the name plate, a docked pet, no draws yet) waits for it and
  // lets the later ones go ahead.
  const tapSettled = done("tap") || (f.tapped && !has("count"));
  if (!done("tap") && f.tapped && has("count")) return "tap";
  if (!STANDALONE && !done("draw") && tapSettled && has("draw")) return "draw";
  // Where the panel comes back from, once it is closed; the statement keeps it open on the first run, and the first
  // step goes before this one.
  const panelSettled = done("panel") || (tapSettled && !has("menu"));
  if (!done("panel") && tapSettled && !f.panelVisible && has("menu")) return "panel";
  if (!done("grip") && panelSettled && !f.panelVisible && has("grip")) return "grip";
  return null;
}

/** Characters of a card's line, for the twelve-character rule. */
export const lineLength = (s: string) => [...s].length;
