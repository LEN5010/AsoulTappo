import { reactive, watch } from "vue";
import { defaultCharacter } from "../characters";

export interface Settings {
  serverUrl: string;
  nick: string;
  character: string;
  /** Pet scale factor relative to the 240x135 base canvas. */
  scale: number;
  mouseFollow: boolean;
  mouseSensitivity: number;
  clickThrough: boolean;
  alwaysOnTop: boolean;
  lastRoom: string;
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
  /** Own pet and panel position on the desktop overlay (CSS px, -1 = default place). */
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
  /** Partners' pets on the desk; off leaves only the own pet. */
  showPartners: boolean;
  /** The strip under the own pet is folded away; a click on the pet shows it for a few seconds. */
  barFolded: boolean;
  /** The strip's handle shows the own name plate on a click and folds the strip on a double click. */
  gripPlate: boolean;
  /** With gripPlate: the own name plate stands where the strip would. */
  barPlate: boolean;
  /** The own pet stands on the bottom edge of the screen: its desk on the edge, the strip hidden. */
  petDocked: boolean;
  /** Global shortcut that hides the pet and the panel and brings them back ("" = none), e.g. "Control+Alt+KeyH". */
  bossKey: string;
  /** Global shortcut that flips click-through ("" = none), in the same form as bossKey. */
  clickThroughKey: string;
  /** The capture window is open: a regular window with the own pet on a flat colour, for OBS and screenshots. */
  captureOpen: boolean;
  /** Background of the capture window, "#rrggbb"; keyed out in the recording software. */
  captureBg: string;
  /** Size of the capture window, CSS px: the size it was last dragged to. */
  captureW: number;
  captureH: number;
  /** Version of the user agreement and privacy policy last agreed to ("" = never); see src/legal. */
  termsAgreed: string;
}

const KEY = "asoultappo.settings.v1";
const LEGACY_SERVER_URL = "http://121.36.224.230:8000";

export const DEFAULT_SETTINGS: Settings = {
  serverUrl: "https://len5010.top/tappo",
  nick: "",
  character: defaultCharacter,
  scale: 1,
  mouseFollow: true,
  mouseSensitivity: 0.3,
  clickThrough: false,
  alwaysOnTop: true,
  lastRoom: "",
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
  petX: -1,
  petY: -1,
  panelX: -1,
  panelY: -1,
  tapView: "today",
  cardAudio: true,
  sfx: true,
  volume: 1,
  shardPop: true,
  showPartners: true,
  barFolded: false,
  gripPlate: false,
  barPlate: false,
  petDocked: false,
  bossKey: "",
  clickThroughKey: "",
  captureOpen: false,
  captureBg: "#00ff00",
  captureW: 560,
  captureH: 412,
  termsAgreed: "",
};

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
    }
  } catch {
    /* corrupted -> defaults */
  }
  // The server moved behind len5010.top; devices still on the old address follow it.
  if (out.serverUrl === LEGACY_SERVER_URL) out.serverUrl = DEFAULT_SETTINGS.serverUrl;
  out.batchMs = Math.min(200, Math.max(100, out.batchMs));
  out.scale = Math.min(3, Math.max(0.5, out.scale));
  out.remoteScale = Math.min(1.5, Math.max(0.4, out.remoteScale));
  out.emoteHoldMs = Math.min(6000, Math.max(1200, out.emoteHoldMs));
  out.volume = Math.min(1, Math.max(0, out.volume));
  out.favorites = Array.isArray(out.favorites)
    ? out.favorites.filter((k): k is string => typeof k === "string").slice(0, 8)
    : [];
  out.showcase = Array.isArray(out.showcase)
    ? [...new Set(out.showcase.filter((k): k is string => typeof k === "string"))].slice(0, 3)
    : [];
  if (out.tapView !== "today" && out.tapView !== "total") out.tapView = "today";
  if (!/^#[0-9a-f]{6}$/i.test(out.captureBg)) out.captureBg = DEFAULT_SETTINGS.captureBg;
  out.captureW = Math.min(1600, Math.max(160, Math.round(out.captureW)));
  out.captureH = Math.min(1600, Math.max(160, Math.round(out.captureH)));
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
