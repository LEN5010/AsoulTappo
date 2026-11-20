// The first-run guide's state in a window (src/guide.ts decides which card is due). The progress is in the settings;
// what the desk has to know of the panel travels in `guideLink` (desktop/bridge.ts carries it between the app's
// windows; the browser preview draws both in one page and shares it).
import { computed, effectScope, reactive, ref, watch } from "vue";
import { dragged } from "../pet/drag";
import { agreed } from "../legal/consent";
import { guideDue, startGuide, withDone, type Card } from "../guide";
import { settings } from "./settings";
import { status } from "./player";
import { readSpotlight, spotlightUnread } from "./spotlight";
import { noticeBoardShown, quietBacklog, releaseChecked, updateDialogOpen, updateOffer } from "./update";

/** What the desk knows of the panel. */
export const guideLink = reactive({
  /** The panel is on screen. */
  panelVisible: false,
  /**
   * The panel's last word on what it opens with: still going. Kept while the panel is hidden or minimized (what is
   * left comes up when it is back); false when no panel was opened this run.
   */
  panelBusy: false,
});

/** The card the desk shows now: the reminders and the other bubbles over the pet wait while one is up. */
export const deskCardShown = ref<Card | null>(null);

/** This run's facts in the desk window. */
export const guideRun = reactive({
  /** The guide started in this run (the desk starts it). */
  started: false,
  /** An input was counted since the terms were agreed to. */
  tapped: false,
});

/** Starts the guide when this version's has not run yet: everyone, once from 1.2.6 on. The desk calls it. */
export function beginGuide(): void {
  if (!guideDue(settings.guide)) return;
  settings.guide = startGuide();
  guideRun.started = true;
}

/** [card] answered: closed, or its place used. */
export function finishCard(card: Card): void {
  if (!settings.guide.done.includes(card)) settings.guide = withDone(settings.guide, card);
}

/**
 * Calls [use] with the `data-guide` name of a place clicked with the main button: pressed and let go without moving
 * off into a drag (a right click, or a drag of a docked pet, does not count). Returns the stop.
 */
export function watchPlaceClicks(use: (place: string) => void): () => void {
  let press: { place: string; x: number; y: number; id: number } | null = null;
  const down = (e: PointerEvent) => {
    const place = e.button === 0 ? (e.target as Element | null)?.closest?.("[data-guide]")?.getAttribute("data-guide") : null;
    press = place ? { place, x: e.clientX, y: e.clientY, id: e.pointerId } : null;
  };
  // The pet's actor takes the pointer once pressed, so the release is told by where it is, not by its target.
  const up = (e: PointerEvent) => {
    const p = press;
    press = null;
    if (p && e.pointerId === p.id && !dragged(e.clientX - p.x, e.clientY - p.y)) use(p.place);
  };
  const cancel = () => { press = null; };
  window.addEventListener("pointerdown", down, true);
  window.addEventListener("pointerup", up, true);
  window.addEventListener("pointercancel", cancel, true);
  return () => {
    window.removeEventListener("pointerdown", down, true);
    window.removeEventListener("pointerup", up, true);
    window.removeEventListener("pointercancel", cancel, true);
  };
}

/**
 * The first consent on this device: what a fresh install would open with all at once is put away, the newest
 * announcement aside. An update keeps its announcements and new skins.
 */
export function quietFirstRun(): void {
  readSpotlight();
  quietBacklog();
}

// ---- the panel's opening queue
/** Parts of the queue held by the components that show them. */
export const panelQueue = reactive({ reward: false, reveal: false });
/**
 * The save's status has come, or the wait for it is over (offline): the update reward is known. Longer than a
 * request's own timeout (net/api.ts), so a slow answer still comes first.
 */
const STATUS_WAIT_MS = 12000;
const statusWaited = ref(false);
let statusTimer: ReturnType<typeof setTimeout> | undefined;
watch(agreed, (ok) => {
  clearTimeout(statusTimer);
  if (ok) statusTimer = setTimeout(() => { statusWaited.value = true; }, STATUS_WAIT_MS);
}, { immediate: true });
/**
 * The panel is still on what it opens with: the terms or the statement, the update check and what it brings (the
 * update, announcements, new skins, the update reward), or a reveal.
 */
export const panelQueueBusy = computed(() =>
  !agreed.value || !releaseChecked.value || (!status.value && !statusWaited.value)
  || (updateDialogOpen.value && !!updateOffer.value) || noticeBoardShown.value || spotlightUnread.value
  || panelQueue.reward || panelQueue.reveal);

/** How long the queue stays empty before the desk hears of it: one dialog closing as the next opens is no gap. */
const IDLE_MS = 500;
let reporting = false;
/**
 * The panel reports its queue to `guideLink` from the first time it comes up for as long as its window is there,
 * hidden or not (desktop/bridge.ts passes it on); in the browser preview, for the rest of the page's life.
 */
export function reportPanelQueue(): void {
  if (reporting) return;
  reporting = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // Detached from the panel component that starts it, which goes away with the panel in the browser preview.
  effectScope(true).run(() => watch(panelQueueBusy, (busy) => {
    clearTimeout(timer);
    if (busy) guideLink.panelBusy = true;
    else timer = setTimeout(() => { guideLink.panelBusy = false; }, IDLE_MS);
  }, { immediate: true }));
}
