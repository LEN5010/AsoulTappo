// Settings travel between the app's windows as patches, so activity updates preserve edits in another window. The
// panel, the todos' window, the race's and the dou dizhu table's send theirs to the desk; the desk sends its own to all of them and passes
// each side window's on to the others.
import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import { windowLabel, type WindowLabel } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import { cleanGuide, mergeGuide } from "../guide";

interface SettingsMessage { from: WindowLabel; patch: Partial<Settings> }
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
  const unlisten = await listen<SettingsMessage>("desktop:settings", ({ payload }) => {
    apply(payload.patch);
    if (windowLabel !== "main") return;
    for (const side of SIDE_WINDOWS) {
      if (side !== payload.from) void emitTo(side, "desktop:settings", { from: "main", patch: payload.patch } satisfies SettingsMessage);
    }
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
    const message: SettingsMessage = { from: windowLabel, patch };
    if (windowLabel === "main") for (const side of SIDE_WINDOWS) void emitTo(side, "desktop:settings", message);
    else void emitTo("main", "desktop:settings", message);
  }, { deep: true, flush: "sync" });
  return { apply, stop: () => { unlisten(); stop(); } };
}
