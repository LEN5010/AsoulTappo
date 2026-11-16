// Settings travel between the app's windows as patches, so activity updates preserve edits in another window. The
// panel and the todos' window send theirs to the desk; the desk sends its own to both and passes each side window's
// on to the other.
import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import { windowLabel, type WindowLabel } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";

interface SettingsMessage { from: WindowLabel; patch: Partial<Settings> }
const SIDE_WINDOWS: WindowLabel[] = ["panel", "todo"];

export async function syncSettings() {
  let receiving = false;
  const apply = (patch: Partial<Settings>) => {
    receiving = true;
    Object.assign(settings, patch);
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
