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
import { ddzBubble } from "./stores/ddz";
import {
  DDZ_HEIGHT, DDZ_WIDTH, DUEL_HEIGHT, DUEL_WIDTH, POKED_HEIGHT, POKED_WIDTH, bubblePlacement, closePick, insidePick, openPick, pickSize,
} from "./pet/duelPick";
import AccessBubble from "./pet/AccessBubble.vue";
import AutoInputBubble from "./pet/AutoInputBubble.vue";
import AutoInputNote from "./pet/AutoInputNote.vue";
import { AUTO_NOTE_HEIGHT, AUTO_NOTE_WIDTH, autoHint, autoNote, autoStrikes, closeAutoHint, openAutoNote } from "./stores/autoHint";
import NamePill from "./pet/NamePill.vue";
import NamePlate from "./pet/NamePlate.vue";
import { getPlate, nameBand, plateSize } from "./pet/plates";
import { STRIP_HEIGHT, ownDeskWidth, remotePetSize, stripFit } from "./pet/bounds";
const MainPanel = defineAsyncComponent(() => import("./panel/MainPanel.vue"));
const RaceFrame = defineAsyncComponent(() => import("./pet/RaceFrame.vue"));
import { PET_BASE, formReach, headAnchor } from "./characters";
import { starterEmotesOf } from "./items";
import { getEmote, characterColor } from "./manifest";
import { settings } from "./stores/settings";
import { counter, followServer, watchDay } from "./stores/counter";
import { onInput, pet, stopPet, tapCooldown } from "./stores/pet";
import { windowVisible } from "./stores/activity";
import { shardCombo } from "./stores/shardPop";
import { draws, online, startReporting, status, stopReporting } from "./stores/player";
import { duel, inRoom, poked, localPet, memberKey, others, roomId, sendEmote, shownNick, type RemoteMember } from "./stores/room";
import { startDebugLog } from "./debugLog";
import { setEmoteKeys } from "./desktop/bossKey";
import { startCapture } from "./desktop/capture";
import {
  DESK_GAP, clamp, defaultFormation, defaultPetPos, dockY, enterRoom, formationCells, formationOffset, inLastRow,
  nextDockSlot, nextSlot, placeFormation, placePet, placeRemote, remotePos, resetOwnPet, rowCols, viewport, type FormationPlace, type Pos,
  type Size,
} from "./stores/desk";
import { openPanel, openTodoWindow, raceFrame, raisePanel, todoFrame, togglePanel, ui } from "./stores/ui";
import { agreed } from "./legal/consent";
import { STANDALONE } from "./edition";
import { updateBusy, updateDialogOpen, updateForced, updateOffer, updatePercent, watchRelease } from "./stores/update";
import { skinVars } from "./stores/theme";
import { startHitReporter } from "./hit";
import {
  debugLogEnabled, isTauri, listenInput, listenInputAccess, listenInputBlocked, listenOutsideClick, listenEmoteKey, listenTodoMoved, listenTray, setAlwaysOnTop,
  setClickThrough, setHotkey, setHitRegions, type InputBlocked,
} from "./composables/tauri";

// ---- viewport
const onResize = () => (viewport.value = { w: window.innerWidth, h: window.innerHeight });
onResize();

// ---- own pet
/** The strip under the own pet: on a pet narrower than its keys need it shrinks to the pet's width as a whole. */
const bar = computed(() => stripFit(settings.scale));
/** The own pet's width: room for the plate's handles beside the pet, wider than the strip (see ownDeskWidth). */
const ownWidth = computed(() => ownDeskWidth(settings.scale));
const ownSize = ref<Size>({ w: PET_BASE.width * settings.scale, h: PET_BASE.height * settings.scale + 30 });
/**
 * Room kept free on the right of a pet for what its second form draws past the picture (an open wing), so the screen
 * edge never cuts it. Kept in both forms, so the pet does not move when it changes. The own pet already has the
 * actor's margin beside it.
 */
const ownReach = computed(() => {
  const s = settings.scale;
  return Math.max(0, Math.ceil(formReach(settings.character) * s - (ownWidth.value - PET_BASE.width * s) / 2));
});
const remoteReach = (m: RemoteMember) => Math.ceil(formReach(m.character) * settings.remoteScale);
const reaching = (size: Size, reach: number): Size => ({ w: size.w + reach, h: size.h });
/** Height of the strip under the pet at full size, measured while it shows; drawn smaller with a shrunken strip. */
const stripNatural = ref(STRIP_HEIGHT);
const stripHeight = computed(() => stripNatural.value * bar.value.zoom);
/** The own pet's size with the strip under it, which a docked or folded pet does not have. */
const fullSize = computed<Size>(() => ({
  w: Math.max(ownSize.value.w, bar.value.width),
  h: Math.round(PET_BASE.height * settings.scale) + stripHeight.value,
}));
/** While the own pet is dragged: whether it would dock where it is now. Null when it is not dragged. */
const dragDock = ref<boolean | null>(null);
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
const ownPos = computed<Pos>(() => {
  if (settings.petDocked) {
    const x = clamp({ x: settings.petX, y: 0 }, reaching(ownSize.value, ownReach.value)).x;
    return peek.value ? clamp({ x, y: dockY(settings.scale) }, reaching(fullSize.value, ownReach.value)) : { x, y: dockY(settings.scale) };
  }
  // Room for the strip is kept under the pet also while the strip is away, so a click can always show it.
  const size = reaching({ w: ownSize.value.w, h: Math.max(ownSize.value.h, fullSize.value.h) }, ownReach.value);
  return settings.petX < 0 ? defaultPetPos(size) : clamp({ x: settings.petX, y: settings.petY }, size);
});
function placeOwnDrag(p: Pos): Pos {
  peek.value = false;
  const placed = placePet(p, reaching(fullSize.value, ownReach.value), settings.scale);
  dragDock.value = placed.docked;
  return placed.pos;
}
function onOwnMoved(p: Pos) {
  settings.petDocked = dragDock.value ?? false;
  dragDock.value = null;
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
      const edge = settings.petDocked ? nextDockSlot(ownPos.value, ownSize.value, remoteSize.value, taken) : null;
      remotePos.set(key, edge ?? nextSlot(ownPos.value, ownSize.value, remoteSize.value, taken));
    }
  },
  { immediate: true },
);
// Formation and row mode: partners stand in rows in the order of `others` (join order), and a drag on any of them
// moves all. A row is a formation as wide as the screen holds that always stands on the bottom edge, so a drag only
// moves it sideways.
const inFormation = computed(() => settings.partnerLayout !== "free");
const inRow = computed(() => settings.partnerLayout === "row");
/** The formation while one of its pets ([by], a member id) is dragged; saved to the settings on release. */
const liveFormation = ref<(FormationPlace & { by: string }) | null>(null);
const formationIndex = computed(() => new Map(shownOthers.value.map((m, i) => [m.id, i])));
const formationCols = computed(() =>
  (inRow.value ? rowCols(shownOthers.value.length, remoteSize.value, viewport.value) : settings.formationCols));
/** Where the formation was left, or null for next to the own pet. */
function savedFormation(n: number, cols: number, size: Size): FormationPlace | null {
  if (inRow.value) {
    if (settings.partnerRowX < 0) return null;
    return placeFormation({ x: settings.partnerRowX, y: 0 }, n, cols, size, settings.remoteScale, viewport.value, true);
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
  const own = { w: ownSize.value.w, h: Math.max(ownSize.value.h, fullSize.value.h) };
  const place = liveFormation.value ?? savedFormation(n, cols, size) ??
    defaultFormation(ownPos.value, own, inRow.value || settings.petDocked, n, cols, size, settings.remoteScale);
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
    settings.remoteScale, viewport.value, inRow.value || undefined,
  );
  liveFormation.value = { ...placed, by: m.id };
  return { x: placed.anchor.x + off.x, y: placed.anchor.y + off.y };
}
function saveFormation() {
  const placed = liveFormation.value;
  if (!placed) return;
  if (inRow.value) {
    settings.partnerRowX = placed.anchor.x;
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
const duelPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DUEL_WIDTH, h: DUEL_HEIGHT }, viewport.value));
const ddzPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: DDZ_WIDTH, h: DDZ_HEIGHT }, viewport.value));
const pokedPlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: POKED_WIDTH, h: POKED_HEIGHT }, viewport.value));
const racePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: RACE_WIDTH, h: RACE_HEIGHT }, viewport.value));
const nudgePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: NUDGE_WIDTH, h: NUDGE_HEIGHT }, viewport.value));
const autoNotePlace = computed(() => bubblePlacement(ownPos.value, ownSize.value, { w: AUTO_NOTE_WIDTH, h: AUTO_NOTE_HEIGHT }, viewport.value));
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
const nearRight = (x: number, scale: number, minEmote: number) =>
  x + 172 * scale + Math.max(minEmote, 72 * scale) + 24 > viewport.value.w;

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
const kick = () => hits?.kick();
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
  if (!agreed.value) openPanel();
  stopDay = watchDay();
  if (isTauri) stopRelease = watchRelease();
  // Reminders wait while the pet is hidden or another bubble holds the spot over it, during a tomato timer's focus
  // and while a todo waits to go up.
  stopNudges = startNudges(() =>
    !windowVisible.value || !!duel.value || !!ddzBubble.value || !!poked.value || !!adminHint.value || accessHint.value || autoShown.value || autoNote.value || tapCooldown.value > Date.now(),
  () => focusing.value || todosWaiting());
  stopPomodoro = startPomodoroClock();
  stopTodos = startTodoClock();
  stopAway = startAway();
  unInput = await listenInput((e) => { onInput(e); noteNudgeInput(); noteAwayInput(e); });
  unOutside = await listenOutsideClick(closeQuickAway);
  unTodoMoved = await listenTodoMoved(keepTodoSpot);
  unEmoteKey = await listenEmoteKey(pickQuickAt);
  unTray = await listenTray((a) => {
    if (a === "toggle-panel") togglePanel();
    else if (a === "open-panel") openPanel();
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
  <div class="desk" :style="skinVars" @dragstart.prevent>
    <PetActor
      v-for="m in shownOthers" :key="m.id" :pos="remoteAt(m)" :label="shownNick(m)"
      :place="(p) => placeRemoteDrag(m, p)" @moved="(p) => onRemoteMoved(m, p)" @dragging="kick" @tap="openPick(m)"
    >
      <PetView
        :character="m.character" :scale="settings.remoteScale" :pulse="m.pulse"
        :motion-id="m.id"
        :emote="m.emote" :combo="m.combo" :win="m.win" :sip="m.sip"
        :flip-bubble="nearRight(remoteAt(m).x, settings.remoteScale, 44)"
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

    <PetActor
      :pos="ownPos" label="我的桌宠" :place="placeOwnDrag" glide data-own-pet :style="{ width: `${ownWidth}px` }"
      @moved="onOwnMoved" @size="onOwnSize" @dragging="kick" @tap="onOwnTap" @pointermove="keepPeek"
    >
      <PetView
        :character="settings.character" :scale="settings.scale" :key-down="pet.keyDown" :form-press="pet.formPress" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
        :left-down="pet.left" :right-down="pet.right"  :emote="localPet.emote" :combo="shardCombo" combo-icon="shard"
        :win="localPet.win" :pulse="localPet.pulse" :sip="localPet.sip"
        :min-emote="56" :flip-bubble="nearRight(ownPos.x, settings.scale, 56)"
      />
      <PomodoroChip v-if="!settings.clickThrough" :style="pomodoroAt" @open="openPomodoro" />
      <!-- The standalone edition has no cooldown, no server notes and no room: only the local bubbles. -->
      <template v-if="!STANDALONE">
        <CooldownBubble :until="autoShown || autoNote ? 0 : tapCooldown" :auto="autoCooling" />
        <ParkNewsBubble :paused="!!duel || !!ddzBubble || !!adminHint || accessHint || autoShown || autoNote || !!nudge" />
      </template>
      <AdminBubble v-if="adminHint" :hint="adminHint" @close="adminHint = null" />
      <template v-if="!STANDALONE">
        <AutoInputBubble v-if="autoShown" @open="openAutoNote()" />
        <AutoInputNote :open="autoNote && !duel && !ddzBubble" :cooling="autoCooling" v-bind="autoNotePlace" @close="closeAutoHint()" />
        <DuelBubble v-bind="duelPlace" />
        <DdzBubble v-if="!duel" v-bind="ddzPlace" />
        <PokeBubble v-if="!duel && !ddzBubble" v-bind="pokedPlace" />
      </template>
      <NudgeBubble v-if="!duel && !ddzBubble && !poked" v-bind="nudgePlace" @todos="openTodo" />
      <RaceBubble v-if="!STANDALONE" v-bind="racePlace" :paused="!!duel || !!ddzBubble || !!poked || !!nudge || autoNote" />
      <AccessBubble v-if="accessHint" @close="accessHint = false" />
      <Transition name="strip" mode="out-in">
      <div v-if="barShown && plateShown" key="plate" class="own-plate">
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
          type="button" class="plate-grip" aria-label="任务栏" :aria-expanded="barPinned ? gripOpen : undefined" @click="onGrip"
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
