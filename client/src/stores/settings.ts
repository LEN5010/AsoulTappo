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
  /** Own pet and panel position on the desktop overlay (CSS px, -1 = default place). */
  petX: number;
  petY: number;
  panelX: number;
  panelY: number;
  sidebarCollapsed: boolean;
  /** Counter bar shows today's or all-time taps. */
  tapView: "today" | "total";
}

const KEY = "asoultappo.settings.v1";

export const DEFAULT_SETTINGS: Settings = {
  serverUrl: "http://121.36.224.230:8000",
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
  petX: -1,
  petY: -1,
  panelX: -1,
  panelY: -1,
  sidebarCollapsed: false,
  tapView: "today",
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
  out.batchMs = Math.min(200, Math.max(100, out.batchMs));
  out.scale = Math.min(3, Math.max(0.5, out.scale));
  out.remoteScale = Math.min(1.5, Math.max(0.4, out.remoteScale));
  out.emoteHoldMs = Math.min(6000, Math.max(1200, out.emoteHoldMs));
  out.favorites = Array.isArray(out.favorites)
    ? out.favorites.filter((k): k is string => typeof k === "string").slice(0, 8)
    : [];
  if (out.tapView !== "today" && out.tapView !== "total") out.tapView = "today";
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
