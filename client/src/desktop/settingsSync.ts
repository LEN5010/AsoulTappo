// Settings travel between the app's windows as patches, so activity updates preserve edits in another window. The
// panel, the todos' window, the race's and the dou dizhu table's send theirs to the desk; the desk takes each in turn
// and sends it on to every side window, the one it came from too, so all of them end on the order the desk took them
// in. The desk sends its own the same way.
import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import { windowLabel, type WindowLabel } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import { cleanGuide, mergeGuide } from "../guide";

interface SettingsMessage {
  from: WindowLabel;
  patch: Partial<Settings>;
  /** A patch the desk passes on: the side window it came from and its number there. */
  origin?: WindowLabel;
  seq?: number;
}
const SIDE_WINDOWS: WindowLabel[] = ["panel", "todo", "race", "ddz"];

export async function syncSettings() {
  let receiving = false;
  const apply = (patch: Partial<Settings>) => {
    receiving = true;
    // The guide's progress meets the local one rather than replacing it: a patch sent before a change made here (a
    // card answered) must not undo it.
    Object.assign(settings, patch.guide ? { ...patch, guide: mergeGuide(settings.guide, cleanGuide(patch.guide)) } : patch);
    receiving = false;
  };
  // A side window's own patches are numbered; for each field, the number of the last one that changed it. The desk
  // sends each back once it took it: an older one of this window's leaves a field alone that a newer one is on its
  // way for, so what is typed is never taken back to what it was a moment ago.
  let sent = 0;
  const pending = new Map<string, number>();
  const confirmed = (patch: Partial<Settings>, seq: number) => Object.fromEntries(Object.entries(patch).filter(([key, v]) => {
    const last = pending.get(key) ?? 0;
    if (last > seq) return false;
    pending.delete(key);
    return JSON.stringify(v) !== JSON.stringify(settings[key as keyof Settings]);
  })) as Partial<Settings>;
  const unlisten = await listen<SettingsMessage>("desktop:settings", ({ payload }) => {
    if (windowLabel !== "main") {
      const own = payload.origin === windowLabel && payload.seq !== undefined;
      apply(own ? confirmed(payload.patch, payload.seq!) : payload.patch);
      return;
    }
    apply(payload.patch);
    const message: SettingsMessage = { from: "main", origin: payload.from, seq: payload.seq, patch: payload.patch };
    for (const side of SIDE_WINDOWS) void emitTo(side, "desktop:settings", message);
  }, { target: windowLabel });
  const stop = watch(() => ({
    ...settings, favorites: [...settings.favorites], showcase: [...settings.showcase], skinNotes: { ...settings.skinNotes },
    // Edited in place, a line at a time.
    reminders: settings.reminders.map((r) => ({ ...r, lines: [...r.lines] })),
    guide: { ...settings.guide, done: [...settings.guide.done] },
  }), (value, old) => {
    if (receiving) return;
    const patch = Object.fromEntries(Object.entries(value).filter(([key, v]) =>
      JSON.stringify(v) !== JSON.stringify(old[key as keyof Settings]),
    ));
    // A write that changed nothing (the same value again) tells no window anything.
    if (!Object.keys(patch).length) return;
    if (windowLabel === "main") {
      const message: SettingsMessage = { from: windowLabel, patch };
      for (const side of SIDE_WINDOWS) void emitTo(side, "desktop:settings", message);
      return;
    }
    sent += 1;
    for (const key of Object.keys(patch)) pending.set(key, sent);
    void emitTo("main", "desktop:settings", { from: windowLabel, patch, seq: sent } satisfies SettingsMessage);
  }, { deep: true, flush: "sync" });
  return { apply, stop: () => { unlisten(); stop(); } };
}
