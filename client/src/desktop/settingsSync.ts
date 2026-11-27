// Settings travel between the app's windows as patches, so activity updates preserve edits in another window. The
// panel, the todos' window, the race's and the dou dizhu table's send theirs to the desk; the desk takes each in turn
// and sends it on to every side window, the one it came from too, so all of them end on the order the desk took them
// in. The desk sends its own the same way.
import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import { windowLabel, type WindowLabel } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import { cleanGuide, mergeGuide, type Guide } from "../guide";
import type { RecentRoom } from "../recentRooms";
import type { Reminder } from "../reminders";

interface SettingsMessage {
  from: WindowLabel;
  patch: Partial<Settings>;
  /** A patch the desk passes on: the side window it came from and its number there. */
  origin?: WindowLabel;
  seq?: number;
}
const SIDE_WINDOWS: WindowLabel[] = ["panel", "todo", "race", "ddz"];

const SETTINGS_KEYS = Object.keys(settings) as (keyof Settings)[];

function sameStringArray(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function sameStringRecord(a: Record<string, string>, b: Record<string, string>): boolean {
  const ka = Object.keys(a);
  if (ka.length !== Object.keys(b).length) return false;
  for (const k of ka) if (a[k] !== b[k]) return false;
  return true;
}

function sameReminders(a: readonly Reminder[], b: readonly Reminder[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i]!;
    const y = b[i]!;
    if (
      x.id !== y.id || x.name !== y.name || x.on !== y.on ||
      x.everyMin !== y.everyMin || x.showSec !== y.showSec || !sameStringArray(x.lines, y.lines)
    ) return false;
  }
  return true;
}

function sameGuide(a: Guide, b: Guide): boolean {
  return a.v === b.v && sameStringArray(a.done, b.done);
}

function sameRecentRooms(a: readonly RecentRoom[], b: readonly RecentRoom[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i]!;
    const y = b[i]!;
    if (x.room !== y.room || x.name !== y.name || x.at !== y.at) return false;
  }
  return true;
}

function sameField<K extends keyof Settings>(key: K, a: Settings[K], b: Settings[K]): boolean {
  switch (key) {
    case "favorites":
    case "showcase":
      return sameStringArray(a as string[], b as string[]);
    case "skinNotes":
      return sameStringRecord(a as Record<string, string>, b as Record<string, string>);
    case "reminders":
      return sameReminders(a as Reminder[], b as Reminder[]);
    case "guide":
      return sameGuide(a as Guide, b as Guide);
    case "recentRooms":
      return sameRecentRooms(a as RecentRoom[], b as RecentRoom[]);
    default:
      return Object.is(a, b);
  }
}

function cloneField<K extends keyof Settings>(s: Settings, key: K): Settings[K] {
  switch (key) {
    case "favorites":
      return [...s.favorites] as Settings[K];
    case "showcase":
      return [...s.showcase] as Settings[K];
    case "skinNotes":
      return { ...s.skinNotes } as Settings[K];
    case "reminders":
      return s.reminders.map((r) => ({ ...r, lines: [...r.lines] })) as Settings[K];
    case "guide":
      return { ...s.guide, done: [...s.guide.done] } as Settings[K];
    case "recentRooms":
      return s.recentRooms.map((r) => ({ ...r })) as Settings[K];
    default:
      return s[key];
  }
}

function snapshot(s: Settings): Settings {
  const out = {} as Record<string, unknown>;
  for (const key of SETTINGS_KEYS) out[key] = cloneField(s, key);
  return out as unknown as Settings;
}

/** The running sync's sender of this window's edits not sent yet. */
let sendPending: (() => void) | undefined;
/**
 * Sends this window's setting edits of this turn now instead of with the next flush: a request to the desk made right
 * after an edit (desktop/transport.ts) then reaches it after the edit, as when each edit went out at once.
 */
export function sendSettingsNow(): void {
  sendPending?.();
}

export async function syncSettings() {
  const prev = snapshot(settings);
  // A side window's own patches are numbered; for each field, the number of the last one that changed it. The desk
  // sends each back once it took it: an older one of this window's leaves a field alone that a newer one is on its
  // way for, so what is typed is never taken back to what it was a moment ago.
  let sent = 0;
  const pending = new Map<string, number>();
  const confirmed = (patch: Partial<Settings>, seq: number) => Object.fromEntries(Object.entries(patch).filter(([key, v]) => {
    const last = pending.get(key) ?? 0;
    if (last > seq) return false;
    pending.delete(key);
    return !sameField(key as keyof Settings, v, settings[key as keyof Settings]);
  })) as Partial<Settings>;
  // Publish same-turn local edits together, or just before taking an incoming patch in the desk's order.
  const sendChanges = () => {
    const patch: Partial<Settings> = {};
    let changed = false;
    for (const key of SETTINGS_KEYS) {
      if (sameField(key, settings[key], prev[key])) continue;
      const copy = cloneField(settings, key);
      (patch as Record<string, unknown>)[key] = copy;
      (prev as unknown as Record<string, unknown>)[key] = copy;
      changed = true;
    }
    // A write that changed nothing (the same value again) tells no window anything.
    if (!changed) return;
    if (windowLabel === "main") {
      const message: SettingsMessage = { from: windowLabel, patch };
      for (const side of SIDE_WINDOWS) void emitTo(side, "desktop:settings", message);
      return;
    }
    sent += 1;
    for (const key of Object.keys(patch)) pending.set(key, sent);
    void emitTo("main", "desktop:settings", { from: windowLabel, patch, seq: sent } satisfies SettingsMessage);
  };
  const receive = (incoming: Partial<Settings>, ownSeq?: number) => {
    sendChanges();
    const patch = ownSeq === undefined ? incoming : confirmed(incoming, ownSeq);
    Object.assign(settings, patch.guide ? { ...patch, guide: mergeGuide(settings.guide, cleanGuide(patch.guide)) } : patch);
    for (const key of Object.keys(patch) as (keyof Settings)[]) {
      (prev as unknown as Record<string, unknown>)[key] = cloneField(settings, key);
    }
  };
  const unlisten = await listen<SettingsMessage>("desktop:settings", ({ payload }) => {
    if (windowLabel !== "main") {
      const own = payload.origin === windowLabel && payload.seq !== undefined;
      receive(payload.patch, own ? payload.seq : undefined);
      return;
    }
    receive(payload.patch);
    const message: SettingsMessage = { from: "main", origin: payload.from, seq: payload.seq, patch: payload.patch };
    for (const side of SIDE_WINDOWS) void emitTo(side, "desktop:settings", message);
  }, { target: windowLabel });
  const stop = watch(settings, sendChanges, { deep: true });
  sendPending = sendChanges;
  return {
    apply: (patch: Partial<Settings>) => receive(patch),
    stop: () => {
      unlisten();
      stop();
      if (sendPending === sendChanges) sendPending = undefined;
    },
  };
}
