import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import * as player from "../stores/player";
import * as room from "../stores/room";
import { counter } from "../stores/counter";
import { tidyRemotes } from "../stores/desk";
import { ui } from "../stores/ui";
import { requestDesktop, type DesktopRequest } from "./transport";

function snapshot() {
  return {
    status: player.status.value, collection: player.collection, online: player.online.value,
    error: player.error.value,
    freshItems: [...player.freshItems], counter: { ...counter },
    conn: room.conn.value, roomId: room.roomId.value, youId: room.youId.value,
    lastError: room.lastError.value, members: [...room.members.values()], emote: room.localPet.emote,
  };
}
type Snapshot = ReturnType<typeof snapshot>;

function applySnapshot(s: Snapshot) {
  player.status.value = s.status;
  Object.assign(player.collection, s.collection);
  player.online.value = s.online;
  player.error.value = s.error;
  player.freshItems.clear();
  s.freshItems.forEach((id) => player.freshItems.add(id));
  Object.assign(counter, s.counter);
  room.conn.value = s.conn;
  room.roomId.value = s.roomId;
  room.youId.value = s.youId;
  room.lastError.value = s.lastError;
  const ids = new Set(s.members.map((m) => m.id));
  for (const id of room.members.keys()) if (!ids.has(id)) room.members.delete(id);
  for (const m of s.members) {
    const existing = room.members.get(m.id);
    if (existing) Object.assign(existing, m);
    else room.members.set(m.id, m);
  }
  room.localPet.emote = s.emote;
}

/** Settings travel as patches so activity updates preserve edits in the panel. */
async function syncSettings() {
  let receiving = false;
  const apply = (patch: Partial<Settings>) => {
    receiving = true;
    Object.assign(settings, patch);
    receiving = false;
  };
  const unlisten = await listen<Partial<Settings>>("desktop:settings", ({ payload }) => apply(payload),
    { target: isPanelWindow ? "panel" : "main" });
  const stop = watch(() => ({ ...settings, favorites: [...settings.favorites] }), (value, old) => {
    if (receiving) return;
    const patch = Object.fromEntries(Object.entries(value).filter(([key, v]) =>
      JSON.stringify(v) !== JSON.stringify(old[key as keyof Settings]),
    ));
    void emitTo(isPanelWindow ? "main" : "panel", "desktop:settings", patch);
  }, { deep: true, flush: "sync" });
  return { apply, stop: () => { unlisten(); stop(); } };
}

/** The panel mirrors state; only the desk window opens sockets and reports activity. */
export async function initDesktop(): Promise<() => void> {
  if (!isTauri) return () => {};
  if (isPanelWindow) {
    const unlisten = await listen<Snapshot>("desktop:state", ({ payload }) => applySnapshot(payload), { target: "panel" });
    const syncedSettings = await syncSettings();
    const initial = await requestDesktop<{ settings: Settings; page: typeof ui.page; craftTarget: string }>("sync");
    syncedSettings.apply(initial.settings);
    ui.page = initial.page;
    ui.craftTarget = initial.craftTarget;
    return () => { unlisten(); syncedSettings.stop(); };
  }

  const publish = () => emitTo("panel", "desktop:state", snapshot());
  const unlisten = await listen<DesktopRequest>("desktop:request", async ({ payload: { id, action, args } }) => {
    try {
      let result: unknown;
      switch (action) {
        case "sync": result = { settings, page: ui.page, craftTarget: ui.craftTarget }; break;
        case "resonate": result = await player.resonate(args[0] as number); break;
        case "craftItem": result = await player.craftItem(args[0] as string); break;
        case "sendEmote": result = room.sendEmote(args[0] as string, args[1] as number); break;
        case "createRoom": result = await room.createRoom(); break;
        case "joinRoom": room.joinRoom(args[0] as string); break;
        case "leaveRoom": room.leaveRoom(); break;
        case "tidyRemotes": tidyRemotes(); break;
      }
      await publish();
      await emitTo("panel", `desktop:reply:${id}`, { result });
    } catch (e) {
      await emitTo("panel", `desktop:reply:${id}`, { error: e instanceof Error ? e.message : String(e) });
    }
  }, { target: "main" });
  const stop = watch(snapshot, () => { void publish(); }, { deep: true });
  const syncedSettings = await syncSettings();
  return () => { unlisten(); stop(); syncedSettings.stop(); };
}
