<script setup lang="ts">
// The desk overlay holds the own pet and room members. Tauri opens the panel in a
// separate regular window; the browser preview keeps it inside the overlay.
// Only the drawn parts take the mouse (see hit.ts); everything else clicks through.
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from "vue";
import PetActor from "./pet/PetActor.vue";
import PetView from "./pet/PetView.vue";
import CounterBar from "./pet/CounterBar.vue";
import QuickEmote from "./pet/QuickEmote.vue";
import StatusDock from "./pet/StatusDock.vue";
import PomodoroDock from "./pet/PomodoroDock.vue";
import GripMenu from "./pet/GripMenu.vue";
import CooldownBubble from "./pet/CooldownBubble.vue";
import ParkNewsBubble from "./pet/ParkNewsBubble.vue";
import AdminBubble from "./pet/AdminBubble.vue";
import DuelBubble from "./pet/DuelBubble.vue";
import PokeBubble from "./pet/PokeBubble.vue";
import NudgeBubble from "./pet/NudgeBubble.vue";
import TodoFrame from "./pet/TodoFrame.vue";
import RaceBubble, { RACE_HEIGHT, RACE_WIDTH } from "./pet/RaceBubble.vue";
import PomodoroChip from "./pet/PomodoroChip.vue";
import { NUDGE_HEIGHT, NUDGE_WIDTH, noteNudgeInput, nudge, startNudges } from "./stores/nudge";
import { noteAwayInput, shownStatus, startAway } from "./stores/away";
import { beginPomodoro, endPomodoro, focusing, notePomodoroPress, pomodoro, startPomodoroClock } from "./stores/pomodoro";
import { todoNow, todos } from "./stores/todo";
import { startTodoClock, todosWaiting } from "./stores/todoClock";
import { isOverdue } from "./todo";
import { wakeAudio } from "./audio/sfx";
import DuelPick from "./pet/DuelPick.vue";
import DdzBubble from "./pet/DdzBubble.vue";
import DdzQueueSign from "./pet/DdzQueueSign.vue";
import DdzSign from "./pet/DdzSign.vue";
import { ddzBubble, ddzMatchable, ddzQueue, ddzQueueSeat, ddzScreen, ddzTables } from "./stores/ddz";
import {
  DDZ_HEIGHT, DDZ_WIDTH, DUEL_HEIGHT, DUEL_WIDTH, POKED_HEIGHT, POKED_WIDTH, bubblePlacement, closePick, insidePick, openPick, pickSize,
  picking,
} from "./pet/duelPick";
import AccessBubble from "./pet/AccessBubble.vue";
import AutoInputBubble from "./pet/AutoInputBubble.vue";
import AutoInputNote from "./pet/AutoInputNote.vue";
import { AUTO_NOTE_HEIGHT, AUTO_NOTE_WIDTH, autoHint, autoNote, autoStrikes, closeAutoHint, openAutoNote } from "./stores/autoHint";
import NamePill from "./pet/NamePill.vue";
import NamePlate from "./pet/NamePlate.vue";
import { getPlate, nameBand, plateSize } from "./pet/plates";
import { PLATE_GRIP, STRIP_HEIGHT, emotePlace, ownDeskWidth, ownXRange, remotePetSize, stripFit } from "./pet/bounds";
import { edgeShift } from "./pet/lift";
import DeskGuide from "./pet/DeskGuide.vue";
import { beginGuide, deskCardShown, guideRun } from "./stores/guide";
import { guideLeft } from "./guide";
const MainPanel = defineAsyncComponent(() => import("./panel/MainPanel.vue"));
const RaceFrame = defineAsyncComponent(() => import("./pet/RaceFrame.vue"));
const DdzFrame = defineAsyncComponent(() => import("./pet/DdzFrame.vue"));
import { PET_BASE, formReach, headAnchor } from "./characters";
import { starterEmotesOf } from "./items";
import { getEmote, characterColor } from "./manifest";
import { settings } from "./stores/settings";
import { counter, followServer, watchDay } from "./stores/counter";
import { onInput, pet, stopPet, tapCooldown } from "./stores/pet";
import { windowVisible } from "./stores/activity";
import { shardCombo } from "./stores/shardPop";
import { draws, online, startReporting, status, stopReporting } from "./stores/player";
import { duel, inRoom, poked, localPet, memberKey, others, rejoinOnStart, roomId, sendEmote, shownNick, type RemoteMember } from "./stores/room";
import { startDebugLog } from "./debugLog";
import { setEmoteKeys } from "./desktop/bossKey";
import { startCapture } from "./desktop/capture";
import {
  DESK_GAP, clamp, defaultFormation, defaultPetPos, dockY, enterRoom, formationCells, formationOffset, inLastRow,
  nextDockSlot, nextSlot, placeFormation, placePet, placeRemote, remotePos, resetOwnPet, viewport, type FormationPlace, type Pos,
  type Size,
} from "./stores/desk";
import { ddzFrame, openPanel, openTodoWindow, raceFrame, raisePanel, todoFrame, togglePanel, ui } from "./stores/ui";
import { agreed } from "./legal/consent";
import { STANDALONE } from "./edition";
import { updateBusy, updateDialogOpen, updateForced, updateOffer, updatePercent, watchRelease } from "./stores/update";
import { skinVars } from "./stores/theme";
import { startHitReporter } from "./hit";
import {
  debugLogEnabled, isTauri, listenInput, listenInputAccess, listenInputBlocked, listenOutsideClick, listenEmoteKey, listenTodoMoved, listenTray, setAlwaysOnTop,
  setClickThrough, setHotkey, setHitRegions, setPanelScale, type InputBlocked,
} from "./composables/tauri";

// ---- viewport
const onResize = () => (viewport.value = { w: window.innerWidth, h: window.innerHeight });
onResize();

// ---- own pet
/** The strip under the own pet: it shrinks to a small pet's width as a whole, or keeps the size set for it. */
const bar = computed(() => stripFit(settings.scale, settings.barFollow ? undefined : settings.barScale));
/** The own pet's width: room for the plate's handles beside the pet, wider than the strip (see ownDeskWidth). */
const ownWidth = computed(() => ownDeskWidth(settings.scale));
/**
 * The band on each side of the own pet in its box that only the plate's handle uses: the mouse goes through it
 * (`data-hit-inset`, hit.ts), the plate takes it with its own row.
 */
const ownBand = computed(() => Math.max(0, Math.floor((ownWidth.value - PET_BASE.width * settings.scale) / 2)));
const ownSize = ref<Size>({ w: PET_BASE.width * settings.scale, h: PET_BASE.height * settings.scale + 30 });
/**
 * Room kept free on the right of a pet for what its second form draws past the picture (an open wing), so the screen
 * edge never cuts it. Kept in both forms, so the pet does not move when it changes. The own pet already has the
 * actor's margin beside it; this is for its first place (defaultPetPos), the side edges go by ownWing.
 */
const ownReach = computed(() => {
  const s = settings.scale;
  return Math.max(0, Math.ceil(formReach(settings.character) * s - (ownWidth.value - PET_BASE.width * s) / 2));
});
/** What the own pet's second form draws past its picture on the right, kept on screen at the right edge. */
const ownWing = computed(() => Math.ceil(formReach(settings.character) * settings.scale));
/**
 * The own pet at [p] kept on screen, [size] its box with the room kept under it: its picture may touch the side edges,
 * the empty bands beside it standing out past the screen (ownXRange); the top and bottom as for any pet.
 */
function keepOwn(p: Pos, size: Size): Pos {
  const { min, max } = ownXRange(size.w, ownBand.value, ownWing.value, viewport.value.w);
  return { x: Math.round(Math.min(Math.max(min, p.x), max)), y: clamp(p, size).y };
}
const remoteReach = (m: RemoteMember) => Math.ceil(formReach(m.character) * settings.remoteScale);
const reaching = (size: Size, reach: number): Size => ({ w: size.w + reach, h: size.h });
/** Height of the strip under the pet at full size, measured while it shows; drawn smaller with a shrunken strip. */
const stripNatural = ref(STRIP_HEIGHT);
const stripHeight = computed(() => stripNatural.value * bar.value.zoom);
/** The own pet's size with the strip under it, which a docked or folded pet does not have. */
const fullSize = computed<Size>(() => ({
  w: ownSize.value.w,
  h: Math.round(PET_BASE.height * settings.scale) + stripHeight.value,
}));
/** While the own pet is dragged: whether it would dock where it is now. Null when it is not dragged. */
const dragDock = ref<boolean | null>(null);
/** The own pet's left edge while it is dragged, null when it is not. */
const dragX = ref<number | null>(null);
const docked = computed(() => dragDock.value ?? settings.petDocked);
/** The strip stays under the pet: not folded away in the settings, and not on the bottom edge where it has no room. */
const barPinned = computed(() => !settings.barFolded && !docked.value);
/** A click on the pet shows an unpinned strip for a few seconds; a docked pet rises off the edge to make room. */
const peek = ref(false);
/** The status keys: under the own name tag, or in place of the quick emotes under the strip. */
const statusOpen = ref(false);
/** The strip's menu, from the handle on a pinned strip or on the own name plate. */
const gripOpen = ref(false);
/** The tomato timer's page: under the own name plate, or in place of the quick emotes under the strip. */
const pomodoroOpen = ref(false);
const PEEK_MS = 6000;
let peekTimer: ReturnType<typeof setTimeout> | undefined;
/** Restarts the countdown; the quick emotes hold the strip open while they are. */
function keepPeek() {
  clearTimeout(peekTimer);
  if (peek.value && !ui.quickOpen && !statusOpen.value && !pomodoroOpen.value) peekTimer = setTimeout(() => (peek.value = false), PEEK_MS);
}
function onOwnTap() {
  if (barPinned.value || settings.clickThrough) return;
  peek.value = !peek.value;
}
const barShown = computed(() => !settings.clickThrough && (barPinned.value || peek.value));
/**
 * How far the strip moves sideways to stay on screen: one wider than the pet stands out beside it, and the pet still
 * reaches the screen's edges. Up to the edges, as the pet's picture: one as wide as the pet stays under it there.
 */
const barShift = computed(() => {
  const x = (dragX.value ?? ownPos.value.x) + (ownWidth.value - bar.value.width) / 2;
  return edgeShift(x, bar.value.width, viewport.value.w, 0);
});
/** The own pet's box with a pinned strip standing out beside it, for placing partners clear of both. */
const ownArea = computed(() => {
  const pos = ownPos.value;
  const left = pos.x + (ownWidth.value - bar.value.width) / 2 + barShift.value;
  if (!barPinned.value || plateShown.value || bar.value.width <= ownWidth.value) return { pos, size: ownSize.value };
  const x = Math.min(pos.x, left);
  return { pos: { x, y: pos.y }, size: { w: Math.max(pos.x + ownSize.value.w, left + bar.value.width) - x, h: ownSize.value.h } };
});
const ownPos = computed<Pos>(() => {
  if (settings.petDocked) {
    const x = keepOwn({ x: settings.petX, y: 0 }, ownSize.value).x;
    return peek.value ? { x, y: clamp({ x, y: dockY(settings.scale) }, fullSize.value).y } : { x, y: dockY(settings.scale) };
  }
  // Room for the strip is kept under the pet also while the strip is away, so a click can always show it.
  const size = { w: ownSize.value.w, h: Math.max(ownSize.value.h, fullSize.value.h) };
  // Not placed yet: petY is -1. Its x may be below 0, the box standing out past the left edge.
  return settings.petY < 0 ? defaultPetPos(reaching(size, ownReach.value)) : keepOwn({ x: settings.petX, y: settings.petY }, size);
});
function placeOwnDrag(p: Pos): Pos {
  peek.value = false;
  const placed = placePet(p, fullSize.value, settings.scale);
  const pos = { x: keepOwn(p, fullSize.value).x, y: placed.pos.y };
  dragDock.value = placed.docked;
  dragX.value = pos.x;
  return pos;
}
function onOwnMoved(p: Pos) {
  settings.petDocked = dragDock.value ?? false;
  dragDock.value = null;
  dragX.value = null;
  settings.petX = p.x;
  settings.petY = p.y;
}
function onOwnSize(size: Size) {
  ownSize.value = size;
  const strip = (size.h - Math.round(PET_BASE.height * settings.scale)) / bar.value.zoom;
  // The plate is lower than the strip; the room kept under the pet stays the strip's, so the pet does not rise.
  if (barShown.value && !plateShown.value && strip > 0 && strip < 80) stripNatural.value = strip;
}
/** Tucks a pinned strip away, pins one a click brought out. A docked pet cannot pin it. */
function toggleFold() {
  settings.barFolded = !settings.barFolded;
  peek.value = false;
}
/** The handle: pins a strip a click on the pet brought out, and opens the strip's menu on a pinned one. */
function onGrip() {
  if (!barPinned.value) return toggleFold();
  gripOpen.value = !gripOpen.value;
  statusOpen.value = ui.quickOpen = false;
}
function foldBar() {
  gripOpen.value = false;
  toggleFold();
}
function swapPlate() {
  gripOpen.value = false;
  settings.barPlate = !settings.barPlate;
  keepPeek();
}
/**
 * The tomato timer's page, from its key on the quick emotes, the strip's menu or the countdown. A strip that is away
 * comes out for it (a docked pet rises off the edge).
 */
function openPomodoro() {
  gripOpen.value = statusOpen.value = false;
  pomodoroOpen.value = true;
  if (!barPinned.value) peek.value = true;
  if (!plateShown.value) ui.quickOpen = true;
}
function closePomodoro() {
  pomodoroOpen.value = ui.quickOpen = false;
}
/** The todos' own window, from its key on the quick emotes, the strip's menu or the bubble for several todos. */
function openTodo() {
  gripOpen.value = statusOpen.value = pomodoroOpen.value = false;
  // The tune of a todo rings here: a press in this window lets it play later.
  if (settings.todoSound) wakeAudio();
  openTodoWindow();
}
/** Where the todos' window was moved to, kept once it rests, so it opens there next time. */
let todoMoved: ReturnType<typeof setTimeout> | undefined;
function keepTodoSpot(x: number, y: number) {
  clearTimeout(todoMoved);
  todoMoved = setTimeout(() => { settings.todoX = x; settings.todoY = y; }, 300);
}
/** A todo is past its time: its key on the quick emotes is tinted. */
const todoLate = computed(() => todos.value.some((t) => isOverdue(t, todoNow.value)));
/** The tray starts and stops the timer without a page: the pet may be hidden. */
function togglePomodoro() {
  if (pomodoro.value) endPomodoro();
  else beginPomodoro();
}
/**
 * The countdown stands over the monitor, centred on its top (PomodoroChip moves itself back by half its width); the
 * pet is centred in the wider actor.
 */
const POMODORO_CHIP_H = 22;
const pomodoroAt = computed(() => {
  const s = settings.scale;
  const petLeft = (ownWidth.value - PET_BASE.width * s) / 2;
  return {
    left: `${Math.round(petLeft + PET_BASE.monitor.x * s)}px`,
    top: `${Math.round(Math.max(0, PET_BASE.monitor.y * s - POMODORO_CHIP_H - 8))}px`,
  };
});
/** The own name plate in the strip's place, as partners see it under this pet; a docked pet keeps the strip. */
const plateShown = computed(() => settings.barPlate && !docked.value);
const ownPlate = computed(() => getPlate(settings.plate)?.id);
const ownPlateSize = computed(() => plateSize(settings.scale));
/** The own name plate (`.own-plate`) and its width with its sides, measured while it shows. */
const plateEl = ref<HTMLElement | null>(null);
const plateWidth = ref(0);
let plateObserver: ResizeObserver | undefined;
watch(plateEl, (el) => {
  plateObserver?.disconnect();
  plateObserver = undefined;
  if (!el) return;
  plateObserver = new ResizeObserver(() => (plateWidth.value = el.offsetWidth));
  plateObserver.observe(el);
});
/**
 * How far the own name plate, centred under the pet, moves sideways to keep its handle and tag on screen: the pet's
 * box may stand out past the screen's edges (keepOwn). The side right of the tag is empty.
 */
const plateShift = computed(() => {
  if (!plateWidth.value) return 0;
  const left = (dragX.value ?? ownPos.value.x) + (ownWidth.value - plateWidth.value) / 2;
  return edgeShift(left, plateWidth.value - PLATE_GRIP, viewport.value.w, 0);
});
const ownName = computed(() => nameBand(settings.scale));
const ownNick = computed(() => settings.nick.trim() || settings.character);
// The room sees the status only while this desk is in one, so the own tag shows it only then too.
const ownStatus = computed(() => (inRoom.value ? shownStatus.value : null));
watch(barShown, (shown) => { if (!shown) ui.quickOpen = statusOpen.value = gripOpen.value = pomodoroOpen.value = false; });
watch(inRoom, (inside) => { if (!inside) statusOpen.value = false; });
watch([peek, () => ui.quickOpen, statusOpen, pomodoroOpen], keepPeek);
// Daily tap statistics and the local counter use the same China calendar day.
watch(() => [status.value?.totals.taps, status.value?.dailyTaps] as const, ([total, daily]) => {
  if (typeof total !== "number") return;
  followServer(total, daily);
}, { immediate: true });
const shownCount = computed(() => (settings.tapView === "today" ? counter.today : counter.total));
const quickKeys = computed(() => (settings.favorites.length ? settings.favorites : starterEmotesOf(settings.character)));

// ---- quick emotes
function pickQuick(key: string) {
  sendEmote(key);
}
/** An emote key: the quick emote at [place] of the strip, counted as the strip shows them. */
function pickQuickAt(place: number) {
  const key = quickKeys.value.filter((k) => getEmote(k))[place - 1];
  if (key) sendEmote(key);
}
function pickStatus(id: string) {
  settings.status = id;
  statusOpen.value = ui.quickOpen = false;
}
function toggleQuick() {
  ui.quickOpen = !ui.quickOpen;
  statusOpen.value = gripOpen.value = pomodoroOpen.value = false;
}
function toggleStatus() {
  statusOpen.value = !statusOpen.value;
  gripOpen.value = pomodoroOpen.value = false;
}
function closeQuick(e: Event) {
  notePomodoroPress();
  const t = e.target as HTMLElement | null;
  // A guide card leaves what it points at as it is.
  if (t?.closest?.("[data-guide-card]")) return;
  if (!t?.closest?.(".dock, .spark, .status-dock, .pomo-dock, .pomo")) ui.quickOpen = false;
  if (!t?.closest?.(".status-dock, .own-tag, .dock, .spark")) statusOpen.value = false;
  if (!t?.closest?.(".pomo-dock, .pomo, .dock, .spark, .grip-menu")) pomodoroOpen.value = false;
  if (!t?.closest?.(".grip-menu, .grip, .plate-grip")) gripOpen.value = false;
  if (!t?.closest?.("[data-own-pet]")) peek.value = false;
  // The duel key over a partner's pet closes on a press anywhere else; a click on a pet shows it again.
  if (!insidePick(e.target)) closePick();
}
const closeOnEscape = (e: KeyboardEvent) => { if (e.key === "Escape") closePick(); };

// ---- other members on the desk
/** Empty with partners hidden: nothing of them is rendered, so they take no clicks either. */
const shownOthers = computed(() => (settings.showPartners ? others.value : []));
const remotePlate = computed(() => plateSize(settings.remoteScale));
const remoteName = computed(() => nameBand(settings.remoteScale));
/** A partner's name plate, when they wear one and plates are shown. */
const plateOf = (m: RemoteMember) => (settings.showPlates ? getPlate(m.plate)?.id : undefined);
const remoteSize = computed<Size>(() => remotePetSize(settings.remoteScale, settings.showNames, settings.showPlates));
watch(roomId, (r) => enterRoom(r), { immediate: true });
// also re-runs when positions are forgotten (enterRoom / tidyRemotes) with the same members
watch(
  () => [others.value.map(memberKey), remotePos.size] as const,
  ([keys]) => {
    for (const key of keys) {
      if (remotePos.has(key)) continue;
      const taken = keys.map((k) => remotePos.get(k)).filter((p): p is Pos => !!p);
      // Next to a docked own pet newcomers stand on the edge too, while it has room.
      const own = ownArea.value;
      const edge = settings.petDocked ? nextDockSlot(own.pos, own.size, remoteSize.value, taken) : null;
      remotePos.set(key, edge ?? nextSlot(own.pos, own.size, remoteSize.value, taken));
    }
  },
  { immediate: true },
);
// Formation and row mode: partners stand in rows in the order of `others` (join order), and a drag on any of them
// moves all. A row is a formation of all partners side by side that always stands on the bottom edge, so a drag only
// moves it sideways; wider than the screen, it runs off the sides and a drag brings either end in.
const inFormation = computed(() => settings.partnerLayout !== "free");
const inRow = computed(() => settings.partnerLayout === "row");
/** The formation while one of its pets ([by], a member id) is dragged; saved to the settings on release. */
const liveFormation = ref<(FormationPlace & { by: string }) | null>(null);
const formationIndex = computed(() => new Map(shownOthers.value.map((m, i) => [m.id, i])));
const formationCols = computed(() =>
  (inRow.value ? Math.max(1, shownOthers.value.length) : settings.formationCols));
/** Where the formation was left, or null for next to the own pet. */
function savedFormation(n: number, cols: number, size: Size): FormationPlace | null {
  if (inRow.value) {
    if (settings.partnerRowX === -1) return null;
    return placeFormation({ x: settings.partnerRowX, y: 0 }, n, cols, size, settings.remoteScale, viewport.value, true, true);
  }
  if (settings.formationX < 0) return null;
  return placeFormation(
    { x: settings.formationX, y: settings.formationY }, n, cols, size, settings.remoteScale, viewport.value,
    settings.formationDocked,
  );
}
const formation = computed(() => {
  const n = shownOthers.value.length;
  const cols = formationCols.value;
  const size = remoteSize.value;
  // The room kept under the own pet for its strip, as ownPos keeps it, so the default place does not jump with it.
  const own = { w: ownArea.value.size.w, h: Math.max(ownSize.value.h, fullSize.value.h) };
  const place = liveFormation.value ?? savedFormation(n, cols, size) ??
    defaultFormation(ownArea.value.pos, own, inRow.value || settings.petDocked, n, cols, size, settings.remoteScale,
      viewport.value, inRow.value);
  return { ...place, n, cells: formationCells(place.anchor, n, cols, size) };
});
// A pet that leaves during its drag never reports the release; the formation then stays where it was saved. A drag
// in one layout is no place in another.
watch([formationIndex, () => settings.partnerLayout], ([index], [, was]) => {
  const live = liveFormation.value;
  if (live && (settings.partnerLayout !== was || !index.has(live.by))) liveFormation.value = null;
});
function dragFormation(m: RemoteMember, p: Pos): Pos {
  const i = formationIndex.value.get(m.id) ?? 0;
  const off = formationOffset(i, formationCols.value, remoteSize.value);
  const placed = placeFormation(
    { x: p.x - off.x, y: p.y - off.y }, shownOthers.value.length, formationCols.value, remoteSize.value,
    settings.remoteScale, viewport.value, inRow.value || undefined, inRow.value,
  );
  liveFormation.value = { ...placed, by: m.id };
  return { x: placed.anchor.x + off.x, y: placed.anchor.y + off.y };
}
function saveFormation() {
  const placed = liveFormation.value;
  if (!placed) return;
  if (inRow.value) {
    // -1 stands for next to the own pet.
    settings.partnerRowX = placed.anchor.x === -1 ? 0 : placed.anchor.x;
  } else {
    settings.formationX = placed.anchor.x;
    settings.formationY = placed.anchor.y;
    settings.formationDocked = placed.docked;
  }
  liveFormation.value = null;
}
const remoteDocked = (m: RemoteMember) => {
  if (!inFormation.value) return !!remotePos.get(memberKey(m))?.docked;
  const f = formation.value;
  return f.docked && inLastRow(formationIndex.value.get(m.id) ?? 0, f.n, formationCols.value);
};
const remoteAt = (m: RemoteMember): Pos => {
  if (inFormation.value) return formation.value.cells[formationIndex.value.get(m.id) ?? 0] ?? ownPos.value;
  const p = remotePos.get(memberKey(m)) ?? ownPos.value;
  const at = clamp(p, reaching(remoteSize.value, remoteReach(m)));
  return remoteDocked(m) ? { x: at.x, y: dockY(settings.remoteScale) } : at;
};
/** A partner docks on the bottom edge like the own pet; in formation and row mode the last row does. */
const placeRemoteDrag = (m: RemoteMember, p: Pos) =>
  inFormation.value ? dragFormation(m, p) : placePet(p, reaching(remoteSize.value, remoteReach(m)), settings.remoteScale).pos;
function onRemoteMoved(m: RemoteMember, p: Pos) {
  if (inFormation.value) return saveFormation();
  const placed = placePet(p, reaching(remoteSize.value, remoteReach(m)), settings.remoteScale);
  placeRemote(memberKey(m), placed.docked ? { ...placed.pos, docked: true } : placed.pos);
}
/** A docked partner's name has no room under the desk; it goes over the desk's front instead. */
const nameOnDesk = (m: RemoteMember) =>
  remoteDocked(m) ? { position: "absolute" as const, bottom: `${Math.round(DESK_GAP * settings.remoteScale) + 4}px` } : undefined;
/** Where the duel bubbles go so they stay on screen: the key and the bets over a partner, the duel over the own pet. */
const pickPlace = (m: RemoteMember) => bubblePlacement(remoteAt(m), remoteSize.value, pickSize(), viewport.value);
/** The open dou dizhu table member [m] opened in the room, shown as a sign over its pet. */
const signOf = (m: RemoteMember) => (ddzMatchable.value
  ? ddzTables.value.find((t) => { const s = t.seats[0]; return !!s && "id" in s && s.id === m.id; }) : undefined);
/** The partner being dragged: its sign, drawn apart from the pet, comes back where it is let go. */
const draggedRemote = ref<string | null>(null);
/** Whether the sign over [m]'s pet shows: not while the pet is dragged, or says something in a bubble of its own. */
const signShown = (m: RemoteMember) => !!signOf(m) && draggedRemote.value !== m.id && !m.emote && !m.win && picking.value !== m.id;
/** The box of [m]'s pet, for the sign to stand on its top edge. */
const signAt = (m: RemoteMember) => {
  const at = remoteAt(m);
  return { transform: `translate(${at.x}px, ${at.y}px)`, width: `${remoteSize.value.w}px` };
};
const duelPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DUEL_WIDTH, h: DUEL_HEIGHT }, viewport.value));
const ddzPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DDZ_WIDTH, h: DDZ_HEIGHT }, viewport.value));
const pokedPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: POKED_WIDTH, h: POKED_HEIGHT }, viewport.value));
const racePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: RACE_WIDTH, h: RACE_HEIGHT }, viewport.value));
const nudgePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: NUDGE_WIDTH, h: NUDGE_HEIGHT }, viewport.value));
const autoNotePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: AUTO_NOTE_WIDTH, h: AUTO_NOTE_HEIGHT }, viewport.value));
/** A guide card at its widest (ui/GuideCard.vue). */
const GUIDE_CARD = { w: 250, h: 72 };
const guidePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, GUIDE_CARD, viewport.value));
/** Bubbles grow to the left when there is no room on the right of the head (see PetView). */
/**
 * Viewport y a plate opened upwards from the own strip stays above: the pet's top, or the top of the emote bubble
 * over its head (PetView's anchor, its 56px floor and the point under it) where that reaches higher.
 */
const plateCeiling = computed(() => {
  const s = settings.scale;
  const bubbleTop = (headAnchor(settings.character).y + 16) * s - Math.max(56, 72 * s) - 12;
  return ownPos.value.y + Math.min(0, bubbleTop);
});
const ownEmote = computed(() => emotePlace(ownPos.value, settings.character, settings.scale, 56, viewport.value));
const remoteEmote = (m: RemoteMember) => emotePlace(remoteAt(m), m.character, settings.remoteScale, 44, viewport.value);

// ---- window, input and tray
let unInput: (() => void) | undefined;
let unTray: (() => void) | undefined;
let unEmoteKey: (() => void) | undefined;
let unOutside: (() => void) | undefined;
let hits: ReturnType<typeof startHitReporter> | undefined;
let stopDebugLog: (() => void) | undefined;
let unBlocked: (() => void) | undefined;
let stopDay: (() => void) | undefined;
let stopRelease: (() => void) | undefined;
let stopCapture: (() => void) | undefined;
let stopNudges: (() => void) | undefined;
let stopAway: (() => void) | undefined;
let stopPomodoro: (() => void) | undefined;
let stopTodos: (() => void) | undefined;
let unTodoMoved: (() => void) | undefined;
// The desk window watches the server's minimum version itself; the panel, which holds the dialog, may never be opened.
watch(updateForced, (must) => { if (must) openPanel(); });
// Shown from the first time an elevated program kept the pet from hearing input, until closed.
const adminHint = ref<InputBlocked | null>(null);
let unAccess: (() => void) | undefined;
// macOS: shown while the hook lacks the input permission, until granted or closed.
const accessHint = ref(false);
// The note that the save's input counts as automatic waits its turn behind the two above and a cooldown's countdown,
// which use the same spot.
// A cooldown for going on after the note is that note's own: the bubble comes first, the countdown once it is read.
const autoCooling = computed(() => autoStrikes.value > 0 && !!status.value?.autoInput);
const autoShown = computed(() => autoHint.value && !autoNote.value && !adminHint.value && !accessHint.value && (!status.value?.tapCooldown || autoCooling.value));
/** Counts the moves the guide's marks follow (ui/GuideMark.vue): a drag, a strip opened or closed. */
const guideTick = ref(0);
const kick = () => {
  hits?.kick();
  guideTick.value++;
};
const deskEl = ref<HTMLElement | null>(null);
/** The guide has cards left: nothing of it runs once every card is answered. */
const guideOn = computed(() => guideLeft(settings.guide));
/** The guide's card waits while another bubble holds the spot over the pet or the pet is hidden. */
const guideHeld = computed(() => !windowVisible.value || !!duel.value || !!ddzBubble.value || !!poked.value || !!adminHint.value
  || accessHint.value || autoShown.value || autoNote.value || !!nudge.value);
/** A click on another window closes the quick emotes: blur where the overlay takes focus, outside-click on Windows where it never does. */
const closeQuickAway = () => {
  ui.quickOpen = statusOpen.value = gripOpen.value = pomodoroOpen.value = false;
  peek.value = false;
  closePick();
};

onMounted(async () => {
  window.addEventListener("resize", onResize);
  window.addEventListener("pointerdown", closeQuick, true);
  window.addEventListener("blur", closeQuickAway);
  window.addEventListener("keydown", closeOnEscape);
  // Reporting and the release watch wait for the terms; the panel holds the dialog that asks for them.
  startReporting();
  // Back into the room the save was in when the app last closed; it waits for the terms too.
  rejoinOnStart();
  beginGuide();
  if (!agreed.value) openPanel();
  stopDay = watchDay();
  if (isTauri) stopRelease = watchRelease();
  // Reminders wait while the pet is hidden or another bubble (a guide card too) holds the spot over it, during a
  // tomato timer's focus and while a todo waits to go up.
  stopNudges = startNudges(() =>
    !windowVisible.value || !!duel.value || !!ddzBubble.value || !!poked.value || !!adminHint.value || accessHint.value || autoShown.value || autoNote.value || tapCooldown.value > Date.now()
      || !!deskCardShown.value,
  () => focusing.value || todosWaiting());
  stopPomodoro = startPomodoroClock();
  stopTodos = startTodoClock();
  stopAway = startAway();
  unInput = await listenInput((e) => {
    onInput(e);
    noteNudgeInput();
    noteAwayInput(e);
    if (agreed.value && (e.kind === "key_down" || e.kind === "mouse_down")) guideRun.tapped = true;
  });
  unOutside = await listenOutsideClick(closeQuickAway);
  unTodoMoved = await listenTodoMoved(keepTodoSpot);
  unEmoteKey = await listenEmoteKey(pickQuickAt);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") togglePanel();
    else if (a === "open-panel") openPanel();
    else if (a === "raise-panel") raisePanel();
    else if (a === "reset-position") resetOwnPet();
    else if (a === "toggle-capture") settings.captureOpen = !settings.captureOpen;
    else if (a === "toggle-pomodoro") togglePomodoro();
    else settings.clickThrough = !settings.clickThrough;
  });
  if (isTauri) hits = startHitReporter((rects, scale) => void setHitRegions(rects, scale));
  else document.documentElement.classList.add("browser-preview");
  unBlocked = await listenInputBlocked((b) => { if (b.by) adminHint.value = b; });
  unAccess = await listenInputAccess((missing) => (accessHint.value = missing));
  if (isTauri) stopCapture = await startCapture();
  if (await debugLogEnabled()) {
    stopDebugLog = startDebugLog(() => `online ${online.value}, in room ${inRoom.value}, ` +
      `click-through ${settings.clickThrough}, always on top ${settings.alwaysOnTop}`);
  }
  // Dev-only look at the update dialog. Production builds drop this branch.
  if (import.meta.env.DEV && !isTauri && new URLSearchParams(location.search).get("preview") === "update") {
    const shot = new URLSearchParams(location.search).get("shot");
    updateOffer.value = {
      version: "0.1.0-beta.7",
      notes: "睡衣派对三款皮肤\n共鸣开包按抽取顺序揭晓",
    };
    updateDialogOpen.value = shot !== "row";
    if (shot === "progress") {
      updateBusy.value = true;
      updatePercent.value = 64;
    }
    openPanel("settings");
  }
});
onBeforeUnmount(() => {
  plateObserver?.disconnect();
  window.removeEventListener("resize", onResize);
  window.removeEventListener("blur", closeQuickAway);
  window.removeEventListener("pointerdown", closeQuick, true);
  window.removeEventListener("keydown", closeOnEscape);
  stopReporting();
  unInput?.();
  unOutside?.();
  unTray?.();
  unEmoteKey?.();
  hits?.stop();
  stopDebugLog?.();
  unBlocked?.();
  stopDay?.();
  stopRelease?.();
  stopCapture?.();
  stopNudges?.();
  stopAway?.();
  stopPomodoro?.();
  stopTodos?.();
  unTodoMoved?.();
  clearTimeout(todoMoved);
  unAccess?.();
  stopPet();
});

watch(() => settings.clickThrough, (v) => setClickThrough(v), { immediate: true });
watch(() => settings.alwaysOnTop, (v) => setAlwaysOnTop(v), { immediate: true });
watch(() => settings.panelScale, (v) => setPanelScale(v), { immediate: true });
// The settings page reports a refused shortcut when it is recorded; at startup it is only in the log.
watch(() => settings.bossKey, (v) => void setHotkey("hide", v).catch(() => {}), { immediate: true });
watch(() => settings.clickThroughKey, (v) => void setHotkey("click-through", v).catch(() => {}), { immediate: true });
watch(() => settings.monitorKey, (v) => void setHotkey("next-monitor", v).catch(() => {}), { immediate: true });
watch(() => settings.emoteKey, (v) => void setEmoteKeys(v, setHotkey).catch(() => {}), { immediate: true });
// While click-through is on the overlay can't receive clicks, so close what needs them.
watch(() => settings.clickThrough, (v) => {
  if (v) {
    ui.quickOpen = statusOpen.value = gripOpen.value = pomodoroOpen.value = false;
  }
});
watch(() => [ui.panelOpen, ui.quickOpen, statusOpen.value, gripOpen.value, pomodoroOpen.value, draws.value, !!pomodoro.value], kick, { flush: "post" });
</script>

<template>
  <div ref="deskEl" class="desk" :style="skinVars" @dragstart.prevent>
    <PetActor
      v-for="m in shownOthers" :key="m.id" :pos="remoteAt(m)" :label="shownNick(m)"
      :place="(p) => placeRemoteDrag(m, p)" @moved="(p) => { draggedRemote = null; onRemoteMoved(m, p); }"
      @dragging="draggedRemote = m.id; kick()" @tap="openPick(m)"
    >
      <PetView
        :character="m.character" :scale="settings.remoteScale" :pulse="m.pulse" :opacity="settings.petOpacity"
        :motion-id="m.id"
        :emote="m.emote" :combo="m.combo" :win="m.win" :sip="m.sip"
        v-bind="remoteEmote(m)"
      />
      <template v-if="settings.showNames">
        <NamePlate
          v-if="plateOf(m)" :card="plateOf(m)!" :nick="shownNick(m)" :color="characterColor(m.character)"
          :width="remotePlate.width" :height="remotePlate.height" :font="remoteName.font" :status="m.status" :style="nameOnDesk(m)"
        />
        <NamePill
          v-else :nick="shownNick(m)" :color="characterColor(m.character)" :width="PET_BASE.width * settings.remoteScale"
          :height="remoteName.pill" :font="remoteName.font" :status="m.status" :style="nameOnDesk(m)"
        />
      </template>
      <DuelPick :id="m.id" v-bind="pickPlace(m)" />
    </PetActor>
    <!-- The signs of open tables, over every partner's pet and under the own pet and its bubbles. -->
    <div class="signs">
      <template v-for="m in shownOthers" :key="m.id">
        <div v-if="signShown(m)" class="sign-at" :style="signAt(m)">
          <DdzSign :key="signOf(m)!.table" :table="signOf(m)!" />
        </div>
      </template>
    </div>

    <PetActor
      :pos="ownPos" label="我的桌宠" :place="placeOwnDrag" glide data-own-pet :data-hit-inset="ownBand" :style="{ width: `${ownWidth}px` }"
      @moved="onOwnMoved" @size="onOwnSize" @dragging="kick" @tap="onOwnTap" @pointermove="keepPeek"
    >
      <PetView
        :character="settings.character" :scale="settings.scale" :key-down="pet.keyDown" :form-press="pet.formPress" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
        :left-down="pet.left" :right-down="pet.right"  :emote="localPet.emote" :combo="shardCombo" combo-icon="shard"
        :win="localPet.win" :pulse="localPet.pulse" :sip="localPet.sip"
        :min-emote="56" :opacity="settings.petOpacity" v-bind="ownEmote"
      />
      <PomodoroChip v-if="!settings.clickThrough" :style="pomodoroAt" @open="openPomodoro" />
      <!-- The standalone edition has no cooldown, no server notes and no room: only the local bubbles. -->
      <template v-if="!STANDALONE">
        <CooldownBubble :until="autoShown || autoNote ? 0 : tapCooldown" :auto="autoCooling" />
        <ParkNewsBubble :paused="!!duel || !!ddzBubble || !!adminHint || accessHint || autoShown || autoNote || !!nudge || !!deskCardShown" />
      </template>
      <AdminBubble v-if="adminHint" :hint="adminHint" @close="adminHint = null" />
      <template v-if="!STANDALONE">
        <AutoInputBubble v-if="autoShown" @open="openAutoNote()" />
        <AutoInputNote :open="autoNote && !duel && !ddzBubble" :cooling="autoCooling" v-bind="autoNotePlace" @close="closeAutoHint()" />
        <DuelBubble v-bind="duelPlace" />
        <DdzBubble v-if="!duel" v-bind="ddzPlace" />
        <!-- While the save waits in the dou dizhu queue, or at the open table the queue seated it at: a sign over the
             head, out of the way of the bubbles. -->
        <div v-if="(ddzQueue || ddzQueueSeat) && !duel && !ddzBubble && !localPet.emote && !localPet.win" class="queue-at">
          <DdzQueueSign />
        </div>
        <PokeBubble v-if="!duel && !ddzBubble" v-bind="pokedPlace" />
      </template>
      <NudgeBubble v-if="!duel && !ddzBubble && !poked" v-bind="nudgePlace" @todos="openTodo" />
      <RaceBubble v-if="!STANDALONE" v-bind="racePlace" :paused="!!duel || !!ddzBubble || !!poked || !!nudge || autoNote || !!deskCardShown" />
      <!-- macOS: the first run of the guide keeps it up. -->
      <AccessBubble v-if="accessHint" :closable="!guideRun.started" @close="accessHint = false" />
      <DeskGuide v-if="guideOn" :held="guideHeld" :cooldown="tapCooldown" v-bind="guidePlace" :scope="deskEl" :tick="guideTick" />
      <Transition name="strip" mode="out-in">
      <div v-if="barShown && plateShown" key="plate" ref="plateEl" class="own-plate" data-hit :style="{ left: `${plateShift}px` }">
        <!-- In a room the tag opens the status keys. -->
        <component
          :is="inRoom ? 'button' : 'div'" class="own-tag"
          v-bind="inRoom ? { type: 'button', 'aria-label': '我的状态', 'aria-expanded': statusOpen } : {}"
          @click="inRoom && toggleStatus()"
        >
          <NamePlate
            v-if="ownPlate" :card="ownPlate" :nick="ownNick" :color="characterColor(settings.character)"
            :width="ownPlateSize.width" :height="ownPlateSize.height" :font="ownName.font" :status="ownStatus"
          />
          <NamePill
            v-else :nick="ownNick" :color="characterColor(settings.character)" :width="PET_BASE.width * settings.scale"
            :height="ownName.pill" :font="ownName.font" :status="ownStatus"
          />
        </component>
        <button
          type="button" class="plate-grip" aria-label="任务栏" :title="barPinned ? '更多' : '固定'"
          :data-guide="barPinned ? 'grip' : undefined"
          :aria-expanded="barPinned ? gripOpen : undefined" @click="onGrip"
        ></button>
        <GripMenu
          v-if="gripOpen" plate :shard-pop="settings.shardPop"
          @fold="foldBar" @swap="swapPlate" @shard-pop="settings.shardPop = !settings.shardPop" @pomodoro="openPomodoro"
          @todo="openTodo"
        />
        <PomodoroDock v-if="pomodoroOpen" :ceiling="plateCeiling" @done="closePomodoro" />
        <StatusDock v-else-if="statusOpen && inRoom" :model-value="settings.status" :ceiling="plateCeiling" @update:model-value="pickStatus" />
      </div>
      <CounterBar
        v-else-if="barShown" key="bar" :count="shownCount" :view="settings.tapView" :width="bar.layout" :zoom="bar.zoom"
        :style="{ left: `${barShift}px` }"
        :quick-open="ui.quickOpen" :draws="STANDALONE ? 0 : draws"
        @toggle-view="settings.tapView = settings.tapView === 'today' ? 'total' : 'today'"
        @quick="toggleQuick" @menu="raisePanel" @resonance="openPanel('resonance')"
        :grip="docked ? undefined : barPinned ? 'menu' : 'pin'" :grip-open="gripOpen" @grip="onGrip"
      >
        <GripMenu
          v-if="gripOpen" :plate="false" :shard-pop="settings.shardPop"
          @fold="foldBar" @swap="swapPlate" @shard-pop="settings.shardPop = !settings.shardPop" @pomodoro="openPomodoro"
          @todo="openTodo"
        />
        <PomodoroDock v-if="ui.quickOpen && pomodoroOpen" :ceiling="plateCeiling" @done="closePomodoro" />
        <StatusDock v-else-if="ui.quickOpen && statusOpen" :model-value="settings.status" :ceiling="plateCeiling" @update:model-value="pickStatus" />
        <QuickEmote
          v-else-if="ui.quickOpen" :keys="quickKeys" :status="ownStatus" :pomodoro="!!pomodoro" :todo="todoLate"
          :ceiling="plateCeiling" @pick="pickQuick" @status="statusOpen = true" @pomodoro="pomodoroOpen = true" @todo="openTodo"
        />
      </CounterBar>
      </Transition>

    </PetActor>

    <Transition name="panel">
      <MainPanel v-if="!isTauri && ui.panelOpen" @reset-pet="resetOwnPet" />
    </Transition>
    <TodoFrame v-if="!isTauri && todoFrame.open" />
    <RaceFrame v-if="!isTauri && raceFrame.open" />
    <DdzFrame v-if="!isTauri && ddzFrame.open && ddzScreen" />
  </div>
</template>

<style>
html, body, #app { margin: 0; width: 100%; height: 100%; background: transparent; overflow: hidden; }
body { font-family: var(--font); color: var(--ink); -webkit-font-smoothing: antialiased; }
/* plain browser preview (npm run dev): show a desktop-like background behind the overlay */
html.browser-preview body {
  background: radial-gradient(1200px 600px at 20% 10%, #cfe0f5, transparent), radial-gradient(900px 600px at 90% 90%, #f3d7e3, transparent), #dfe6ef;
}
</style>

<style scoped>
/* Nothing on the desk is selectable or draggable by the webview itself (template: dragstart), so pets leave no
   selection box or drag picture behind. */
.desk { position: fixed; inset: 0; pointer-events: none; -webkit-user-select: none; user-select: none; }
/* The strip comes out from under the desk and goes back there. It keeps its place in the layout while leaving. */
.strip-enter-active { transition: opacity var(--dur-base) var(--ease-out), translate var(--dur-slow) var(--ease-spring); }
.strip-leave-active { transition: opacity var(--dur-fast) var(--ease-in), translate var(--dur-release) var(--ease-in); }
/* A shrunken strip (CounterBar's --bar-zoom) slides by as much less. */
.strip-enter-from, .strip-leave-to { opacity: 0; translate: 0 calc(-14px * var(--bar-zoom, 1)); }
.desk > :deep(*) { pointer-events: auto; }
/* A layer of no size of its own; each sign stands on the top edge of its pet's box. */
.signs, .sign-at { position: absolute; left: 0; top: 0; height: 0; }
.queue-at { position: absolute; left: 0; right: 0; top: 0; height: 0; z-index: 2; }
.signs { width: 0; }
/* The own name plate in the strip's place, the handle on its left like the strip's: a short white line that reads
 * on any wallpaper. The side padding keeps the plate centred under the pet. */
.own-plate {
  position: relative;
  display: flex;
  padding: 2px 14px 0;
}
.own-tag {
  display: flex;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: inherit;
}
button.own-tag {
  cursor: pointer;
}
/* The tag starts at the plate's top padding, as tall as the handle beside it. */
.own-tag > .pill {
  margin-top: 0;
}
.plate-grip {
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 0;
  width: 14px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
}
.plate-grip::before {
  content: "";
  position: absolute;
  left: 5px;
  top: 50%;
  width: 4px;
  height: 14px;
  translate: 0 -50%;
  border-radius: 2px;
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(var(--shadow-rgb), 0.45);
  transition: background var(--dur-fast), height var(--dur-fast) var(--ease-out);
}
.plate-grip:hover::before { height: 20px; background: var(--c-500); }
</style>
