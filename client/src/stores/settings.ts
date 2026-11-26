import { reactive, watch } from "vue";
import { readRecentRooms, type RecentRoom } from "../recentRooms";
import { defaultCharacter } from "../characters";
import { MAX_SHOWCASE } from "../net/protocol";
import { cleanReminders, type Reminder } from "../reminders";
import { roomStatus } from "../roomStatus";
import { isTauri } from "../composables/tauri";
import { STANDALONE } from "../edition";
import { cleanGuide, mergeGuide, type Guide } from "../guide";

export interface Settings {
  serverUrl: string;
  nick: string;
  character: string;
  /** Pet scale factor relative to the 240x135 base canvas. */
  scale: number;
  /** How much of the pets' figures shows on the desk, 0.3 to 1; bubbles, names and the strip stay solid. */
  petOpacity: number;
  mouseFollow: boolean;
  mouseSensitivity: number;
  clickThrough: boolean;
  alwaysOnTop: boolean;
  lastRoom: string;
  /** The room the save was in when the app last closed ("" = none): the desk goes back into it once on start. */
  rejoinRoom: string;
  /** The rooms joined lately, newest first (recentRooms.ts). */
  recentRooms: RecentRoom[];
  /** Tap batching window (100–200ms). */
  batchMs: number;
  /** Quick emotes mirrored to the server. */
  favorites: string[];
  /** How long an emote bubble stays (ms). */
  emoteHoldMs: number;
  /** Size of other members' pets relative to the base canvas. */
  remoteScale: number;
  showNames: boolean;
  /** Partners' name plates; off shows their plain name tags. */
  showPlates: boolean;
  /** Shows partners by their pet's member name instead of their nickname, for streaming. */
  hideNicks: boolean;
  /** Name plate worn on partners' desks: a big hidden card id or a manifest `plates` id ("" = none). */
  plate: string;
  /** Card ids pinned to the profile room members open, at most three, in order. */
  showcase: string[];
  /** Ranked on the collection board (the 排行 page); off keeps the save off it. */
  onBoard: boolean;
  /** Turns down every rock-paper-scissors invite; the room server answers them for this client. */
  duelDnd: boolean;
  /** The status shown to rooms: a `ROOM_STATUSES` id, "" for none. */
  status: string;
  /**
   * Own pet and panel position on the desktop overlay (CSS px, -1 = default place). The own pet's petY says it: its petX
   * may be below 0, its box standing out past the left edge.
   */
  petX: number;
  petY: number;
  panelX: number;
  panelY: number;
  /** Counter bar shows today's or all-time taps. */
  tapView: "today" | "total";
  /** Dynamic cards play their own sound in the reveal and the card preview. */
  cardAudio: boolean;
  /** Synthesized interface sounds: page turns, card flips, the alpaca. */
  sfx: boolean;
  /** Loudness of card audio and interface sounds, 0 to 1. */
  volume: number;
  /** "+N" shards over the own pet while typing. */
  shardPop: boolean;
  /** The own pet's reminders as a whole (src/nudge.ts): off, none of the ones below comes up. */
  healthTips: boolean;
  /** The reminders that come after some time at the computer: the built-in ones and the player's own (src/reminders.ts). */
  reminders: Reminder[];
  /** The once-a-day ones: the hello, the lunch question and the bedtime line. */
  tipGreet: boolean;
  tipLunch: boolean;
  tipNight: boolean;
  /** Tomato timer lengths in minutes: the focus (5–120) and the rest (1–60). */
  pomodoroFocus: number;
  pomodoroRest: number;
  /** A longer rest every few rounds (src/pomodoro.ts). */
  pomodoroLong: boolean;
  /** The next focus starts by itself after the rest; off, the pet asks first. */
  pomodoroAuto: boolean;
  /** A short tune when a focus or a rest ends. */
  pomodoroSound: boolean;
  /** A notice from the system too when a focus or a rest ends, seen while the pet is hidden or a game fills the screen. */
  pomodoroNotify: boolean;
  /** The tomato timer's tune when a todo comes due (stores/todo.ts). */
  todoSound: boolean;
  /** A notice from the system too when a todo comes due. */
  todoNotify: boolean;
  /** The pet says so when a dumpling race starts, with a key to watch it (pet/RaceBubble.vue). */
  raceRemind: boolean;
  /** The todos' window stays over other windows. */
  todoPinned: boolean;
  /** Where the todos' window was left: its top left corner in screen pixels; both -1 before it was first moved. */
  todoX: number;
  todoY: number;
  /** The todos' window's size in logical pixels, set by the grip at its corner (TODO_MIN to TODO_MAX). */
  todoW: number;
  todoH: number;
  /** Partners' pets on the desk; off leaves only the own pet. */
  showPartners: boolean;
  /**
   * How partners stand: each where it was dragged ("free"), side by side on the bottom edge ("row"), or together in
   * rows that move as one ("formation").
   */
  partnerLayout: PartnerLayout;
  /** Pets per row of the formation (1–10). */
  formationCols: number;
  /** Top-left of the formation (CSS px, -1 = next to the own pet). */
  formationX: number;
  formationY: number;
  /** The formation's last row stands on the bottom edge of the screen. */
  formationDocked: boolean;
  /** Left of the row of partners on the bottom edge (CSS px, -1 = next to the own pet); below -1 a row wider than the
   * screen starts left of it. */
  partnerRowX: number;
  /** The strip under the own pet is folded away; a click on the pet shows it for a few seconds. */
  barFolded: boolean;
  /** The strip shrinks with a small own pet; off, it keeps the size of `barScale` whatever the pet's. */
  barFollow: boolean;
  /** Scale of the strip while `barFollow` is off. */
  barScale: number;
  /** The own name plate stands where the strip would (swapped from the strip's menu). */
  barPlate: boolean;
  /** The own pet stands on the bottom edge of the screen: its desk on the edge, the strip hidden. */
  petDocked: boolean;
  /** Global shortcut that hides the pet and the panel and brings them back ("" = none), e.g. "Control+Alt+KeyH". */
  bossKey: string;
  /** Global shortcut that flips click-through ("" = none), in the same form as bossKey. */
  clickThroughKey: string;
  /** Global shortcut that moves the pet to the next monitor as the tray does ("" = none), in the same form as bossKey. */
  monitorKey: string;
  /** Modifiers of the emote keys ("" = none), e.g. "Control+Alt": with 1 to 8 they play the quick emote at that place. */
  emoteKey: string;
  /** The capture window is open: a regular window with the own pet on a flat colour, for OBS and screenshots. */
  captureOpen: boolean;
  /** Background of the capture window, "#rrggbb"; keyed out in the recording software. */
  captureBg: string;
  /** Size of the capture window, CSS px: the size it was last dragged to. */
  captureW: number;
  captureH: number;
  /** Version of the user agreement and privacy policy last agreed to ("" = never); see src/legal. */
  termsAgreed: string;
  /** App version whose free-of-charge statement was last confirmed ("" = never); asked again by every new version. */
  statementSeen: string;
  /**
   * The standalone edition's own: app version whose standalone statement was last confirmed ("" = never). Kept apart
   * from statementSeen, so the two editions never confirm for each other.
   */
  standaloneStatementSeen: string;
  /** The mystery key in About has been opened; until then its sparkle twinkles now and then. */
  promoSeen: boolean;
  /** What the feedback dialog holds unsent: the text and the contact, kept until a send goes through. */
  feedbackText: string;
  feedbackContact: string;
  /** Names the player gave their own skins, by skin id (stores/skinNotes.ts). */
  skinNotes: Record<string, string>;
  /** The first-run guide's progress (src/guide.ts); replaced as a whole, never changed in place. */
  guide: Guide;
}

const KEY = "asoultappo.settings.v1";

/** The partner layouts in the order the online page lists them. */
export const PARTNER_LAYOUTS = ["free", "row", "formation"] as const;
export type PartnerLayout = (typeof PARTNER_LAYOUTS)[number];
/** How partners are named: their nickname, their pet's member name (for streaming), or no name tag on the desk. */
export type PartnerNames = "nick" | "member" | "off";
export const partnerNames = (s: Pick<Settings, "showNames" | "hideNicks">): PartnerNames =>
  !s.showNames ? "off" : s.hideNicks ? "member" : "nick";
export function setPartnerNames(s: Pick<Settings, "showNames" | "hideNicks">, v: PartnerNames) {
  s.showNames = v !== "off";
  s.hideNicks = v === "member";
}
/** Longest skin note, in characters. */
export const SKIN_NOTE_MAX = 10;
const LEGACY_SERVER_URL = "http://121.36.224.230:8000";

/** The todos' window's size limits: below the minimum the time picker no longer fits. */
export const TODO_MIN = { w: 280, h: 340 } as const;
export const TODO_MAX = { w: 800, h: 1200 } as const;
export const todoSize = (v: number, side: "w" | "h") =>
  Math.round(Math.min(TODO_MAX[side], Math.max(TODO_MIN[side], Number.isFinite(v) ? v : TODO_MIN[side])));

export const DEFAULT_SETTINGS: Settings = {
  // The standalone edition has no server (src/edition.ts).
  serverUrl: STANDALONE ? "" : "https://len5010.top/tappo",
  nick: "",
  character: defaultCharacter,
  scale: 1,
  petOpacity: 1,
  mouseFollow: true,
  mouseSensitivity: 0.3,
  clickThrough: false,
  alwaysOnTop: true,
  lastRoom: "",
  rejoinRoom: "",
  recentRooms: [],
  batchMs: 150,
  favorites: [],
  emoteHoldMs: 2500,
  remoteScale: 1,
  showNames: true,
  showPlates: true,
  hideNicks: false,
  plate: "",
  showcase: [],
  onBoard: true,
  duelDnd: false,
  status: "",
  petX: -1,
  petY: -1,
  panelX: -1,
  panelY: -1,
  tapView: "today",
  cardAudio: true,
  sfx: true,
  volume: 1,
  shardPop: true,
  healthTips: true,
  reminders: cleanReminders(undefined),
  tipGreet: true,
  tipLunch: true,
  tipNight: true,
  pomodoroFocus: 25,
  pomodoroRest: 5,
  pomodoroLong: true,
  pomodoroAuto: false,
  pomodoroSound: true,
  pomodoroNotify: false,
  todoSound: true,
  todoNotify: false,
  raceRemind: false,
  todoPinned: true,
  todoX: -1,
  todoY: -1,
  todoW: 320,
  todoH: 460,
  showPartners: true,
  partnerLayout: "free",
  formationCols: 5,
  formationX: -1,
  formationY: -1,
  formationDocked: false,
  partnerRowX: -1,
  barFolded: false,
  barFollow: true,
  barScale: 1,
  barPlate: false,
  petDocked: false,
  bossKey: "",
  clickThroughKey: "",
  monitorKey: "",
  emoteKey: "",
  captureOpen: false,
  captureBg: "#00ff00",
  captureW: 560,
  captureH: 412,
  termsAgreed: "",
  statementSeen: "",
  standaloneStatementSeen: "",
  promoSeen: false,
  feedbackText: "",
  feedbackContact: "",
  skinNotes: {},
  guide: cleanGuide(undefined),
};

/** A note as it is kept: trimmed and at most SKIN_NOTE_MAX characters. */
export const cleanSkinNote = (text: string) => [...text.trim()].slice(0, SKIN_NOTE_MAX).join("");

function cleanSkinNotes(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  for (const [name, text] of Object.entries(raw).slice(0, 64)) {
    const note = typeof text === "string" ? cleanSkinNote(text) : "";
    if (note && name.length <= 32) out[name] = note;
  }
  return out;
}

export function loadSettings(storage: Pick<Storage, "getItem"> | undefined = globalThis.localStorage): Settings {
  const out: Settings = { ...DEFAULT_SETTINGS };
  try {
    const raw = storage?.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Settings>;
      for (const k of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
        if (typeof parsed[k] === typeof DEFAULT_SETTINGS[k] && parsed[k] !== undefined) {
          (out as unknown as Record<string, unknown>)[k] = parsed[k];
        }
      }
      // Up to 1.2: the plate came up only with the handle's plate setting on; with it off a plate left up stays down.
      if ("gripPlate" in parsed && (parsed as { gripPlate?: unknown }).gripPlate !== true) out.barPlate = false;
    }
  } catch {
    /* corrupted -> defaults */
  }
  // The server moved behind len5010.top; devices still on the old address follow it.
  if (STANDALONE) out.serverUrl = "";
  else if (out.serverUrl === LEGACY_SERVER_URL) out.serverUrl = DEFAULT_SETTINGS.serverUrl;
  out.batchMs = Math.min(200, Math.max(100, out.batchMs));
  out.scale = Math.min(3, Math.max(0.5, out.scale));
  out.petOpacity = Math.min(1, Math.max(0.3, out.petOpacity));
  out.remoteScale = Math.min(1.5, Math.max(0.4, out.remoteScale));
  out.barScale = Math.min(1.5, Math.max(0.6, out.barScale));
  out.emoteHoldMs = Math.min(6000, Math.max(1200, out.emoteHoldMs));
  out.volume = Math.min(1, Math.max(0, out.volume));
  out.pomodoroFocus = Math.min(120, Math.max(5, Math.round(out.pomodoroFocus)));
  out.pomodoroRest = Math.min(60, Math.max(1, Math.round(out.pomodoroRest)));
  out.recentRooms = readRecentRooms(out.recentRooms);
  out.favorites = Array.isArray(out.favorites)
    ? out.favorites.filter((k): k is string => typeof k === "string").slice(0, 8)
    : [];
  out.showcase = Array.isArray(out.showcase)
    ? [...new Set(out.showcase.filter((k): k is string => typeof k === "string"))].slice(0, MAX_SHOWCASE)
    : [];
  if (out.tapView !== "today" && out.tapView !== "total") out.tapView = "today";
  if (!PARTNER_LAYOUTS.includes(out.partnerLayout)) out.partnerLayout = "free";
  // Up to 1.2.5 both switches could be on with the nicknames switch out of sight; no names wins.
  if (!out.showNames) out.hideNicks = false;
  out.formationCols = Math.min(10, Math.max(1, Math.round(out.formationCols)));
  out.formationX = Math.max(-1, Math.round(out.formationX));
  out.formationY = Math.max(-1, Math.round(out.formationY));
  out.partnerRowX = Math.round(out.partnerRowX);
  // Screen pixels may be negative left of or above the main monitor.
  out.todoX = Math.round(out.todoX);
  out.todoY = Math.round(out.todoY);
  out.todoW = todoSize(out.todoW, "w");
  out.todoH = todoSize(out.todoH, "h");
  if (!roomStatus(out.status)) out.status = "";
  if (!/^#[0-9a-f]{6}$/i.test(out.captureBg)) out.captureBg = DEFAULT_SETTINGS.captureBg;
  out.captureW = Math.min(1600, Math.max(160, Math.round(out.captureW)));
  out.captureH = Math.min(1600, Math.max(160, Math.round(out.captureH)));
  out.skinNotes = cleanSkinNotes(out.skinNotes);
  // As long as the server takes them (stores/feedback.ts).
  out.feedbackText = out.feedbackText.slice(0, 1000);
  out.feedbackContact = out.feedbackContact.slice(0, 100);
  out.reminders = cleanReminders(out.reminders);
  // Missing up to 1.2.5: the guide then starts.
  out.guide = cleanGuide(out.guide);
  return out;
}

export const settings = reactive<Settings>(loadSettings());

watch(
  settings,
  (v) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(v));
    } catch {
      /* storage unavailable */
    }
  },
  { deep: true },
);

// The browser preview opens the todos' window as a popup of the same origin: each page follows the settings the
// other one writes. The app's windows pass theirs through the desk instead (desktop/settingsSync.ts).
if (!isTauri && typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY || !e.newValue) return;
    const loaded = loadSettings();
    Object.assign(settings, { ...loaded, guide: mergeGuide(settings.guide, loaded.guide) });
  });
}
