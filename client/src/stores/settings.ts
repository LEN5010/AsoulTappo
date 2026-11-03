import { reactive, watch } from "vue";
import { defaultCharacter } from "../characters";
import manifest from "../data/manifest.json";

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
  /** Selected theme id (see data/manifest.json). */
  theme: string;
  /** Tap batching window (100–200ms). */
  batchMs: number;
}

const KEY = "asoultappo.settings.v1";

export const DEFAULT_SETTINGS: Settings = {
  serverUrl: "http://localhost:8000",
  nick: "",
  character: defaultCharacter,
  scale: 1,
  mouseFollow: true,
  mouseSensitivity: 0.3,
  clickThrough: false,
  alwaysOnTop: true,
  lastRoom: "",
  theme: manifest.defaultTheme,
  batchMs: 150,
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
