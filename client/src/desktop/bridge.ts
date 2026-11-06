import { emitTo, listen } from "@tauri-apps/api/event";
import { ref, watch } from "vue";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import * as player from "../stores/player";
import * as room from "../stores/room";
import { restingMotion } from "../net/protocol";
import { counter } from "../stores/counter";
import { tidyRemotes } from "../stores/desk";
import { ui } from "../stores/ui";
import { requestDesktop, type DesktopRequest } from "./transport";

const groupSources = {
  player: () => ({ status: player.status.value, online: player.online.value, error: player.error.value }),
  collection: () => player.collection,
  freshItems: () => [...player.freshItems], counter: () => ({ ...counter }),
  room: () => ({ conn: room.conn.value, roomId: room.roomId.value, youId: room.youId.value, lastError: room.lastError.value }),
  members: () => [...room.members.values()].map(({ id, uid, nick, character, frame, badge, head, desk }) =>
    ({ id, uid, nick, character, frame, badge, head, desk })),
};
function groups() {
  return { player: groupSources.player(), collection: groupSources.collection(), freshItems: groupSources.freshItems(),
    counter: groupSources.counter(), room: groupSources.room(), members: groupSources.members() };
}
const groupsFor = <K extends keyof Groups>(key: K) => groupSources[key]();
type Groups = ReturnType<typeof groups>;
type Runtime = Pick<room.RemoteMember, "id" | "motion" | "taps" | "pulse" | "emote" | "combo">;
const runtime = (m: room.RemoteMember): Runtime => ({
  id: m.id, motion: { ...m.motion }, taps: m.taps, pulse: m.pulse, emote: m.emote, combo: m.combo,
});
const pendingRuntime = new Map<string, Runtime>();
function applyGroups(s: Partial<Groups>) {
  if (s.player) {
    player.status.value = s.player.status;
    player.online.value = s.player.online;
    player.error.value = s.player.error;
  }
  if (s.collection) Object.assign(player.collection, s.collection);
  if (s.freshItems) {
    player.freshItems.clear();
    s.freshItems.forEach((id) => player.freshItems.add(id));
  }
  if (s.counter) Object.assign(counter, s.counter);
  if (s.room) {
    room.conn.value = s.room.conn;
    room.roomId.value = s.room.roomId;
    room.youId.value = s.room.youId;
    room.lastError.value = s.room.lastError;
  }
  if (s.members) {
    const ids = new Set(s.members.map((m) => m.id));
    for (const id of room.members.keys()) if (!ids.has(id)) {
      room.members.delete(id);
      pendingRuntime.delete(id);
    }
    for (const m of s.members) {
      const pose = pendingRuntime.get(m.id);
      const existing = room.members.get(m.id);
      if (existing) Object.assign(existing, m, pose);
      else room.members.set(m.id, { ...m, taps: 0, pulse: 0, emote: null, combo: null, motion: restingMotion(), ...pose });
      if (pose) pendingRuntime.delete(m.id);
    }
  }
}
function applyRuntime(updates: Runtime[], emote: typeof room.localPet.emote) {
  for (const update of updates) {
    const member = room.members.get(update.id);
    if (member) Object.assign(member, update);
    else pendingRuntime.set(update.id, update);
  }
  room.localPet.emote = emote;
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

/** The desk owns network state; the visible panel subscribes to independent slices. */
export async function initDesktop(): Promise<() => void> {
  if (!isTauri) return () => {};
  if (isPanelWindow) {
    const unState = await listen<Partial<Groups>>("desktop:state", ({ payload }) => applyGroups(payload), { target: "panel" });
    const unMotion = await listen<{ members: Runtime[]; emote: typeof room.localPet.emote }>("desktop:motion",
      ({ payload }) => applyRuntime(payload.members, payload.emote), { target: "panel" });
    const syncedSettings = await syncSettings();
    const initial = await requestDesktop<{ settings: Settings; page: typeof ui.page; craftTarget: string; state: Groups }>("sync");
    syncedSettings.apply(initial.settings);
    applyGroups(initial.state);
    ui.page = initial.page;
    ui.craftTarget = initial.craftTarget;
    const stop = watch(() => [ui.panelOpen && !ui.panelMinimized, ui.page === "room"] as const,
      ([visible, live]) => { void emitTo("main", "desktop:interest", { visible, live }); }, { immediate: true });
    return () => { unState(); unMotion(); stop(); syncedSettings.stop(); };
  }

  const visibleRef = ref(false);
  const liveRef = ref(false);
  let visible = false;
  let live = false;
  let pending: Partial<Groups> = {};
  const dirty = new Map<string, Runtime>();
  let motionTimer: ReturnType<typeof setTimeout> | undefined;
  let stateTimer: ReturnType<typeof setTimeout> | undefined;
  const publish = async () => {
    clearTimeout(stateTimer);
    stateTimer = undefined;
    const patch = pending;
    pending = {};
    if (Object.keys(patch).length) await emitTo("panel", "desktop:state", patch);
  };
  const stops = (Object.keys(groups()) as (keyof Groups)[]).map((key) => watch(
    () => visibleRef.value ? groupsFor(key) : undefined,
    (value) => {
      if (value === undefined) return;
      Object.assign(pending, { [key]: value });
      stateTimer ??= setTimeout(() => { void publish(); }, 50);
    }, { deep: true, flush: "sync" },
  ));
  function sendMotion() {
    motionTimer = undefined;
    if (!visible || !live) return;
    const updates = [...dirty.values()];
    dirty.clear();
    void emitTo("panel", "desktop:motion", { members: updates, emote: room.localPet.emote });
  }
  const memberStops = new Map<string, () => void>();
  const stopMembers = watch(() => liveRef.value ? [...room.members.keys()] : [], (ids) => {
    for (const [id, stop] of memberStops) if (!ids.includes(id)) { stop(); memberStops.delete(id); dirty.delete(id); }
    for (const id of ids) if (!memberStops.has(id)) {
      memberStops.set(id, watch(() => {
        const member = room.members.get(id);
        return member ? runtime(member) : null;
      }, (value) => {
        if (!value) { dirty.delete(id); return; }
        dirty.set(id, value);
        motionTimer ??= setTimeout(sendMotion, 50);
      }, { deep: true, immediate: true, flush: "sync" }));
    }
  }, { flush: "sync" });
  const stopEmote = watch(() => liveRef.value ? room.localPet.emote : null, () => {
    if (liveRef.value) motionTimer ??= setTimeout(sendMotion, 50);
  }, { deep: true });
  const unInterest = await listen<{ visible: boolean; live: boolean }>("desktop:interest", async ({ payload }) => {
    const opening = payload.visible && !visible;
    visible = payload.visible;
    live = visible && payload.live;
    visibleRef.value = visible;
    liveRef.value = live;
    if (!visible) {
      pending = {}; dirty.clear(); clearTimeout(stateTimer); clearTimeout(motionTimer);
      stateTimer = motionTimer = undefined;
    } else if (opening) {
      pending = groups();
      await publish();
    }
  }, { target: "main" });
  const unlisten = await listen<DesktopRequest>("desktop:request", async ({ payload: { id, action, args } }) => {
    try {
      let result: unknown;
      switch (action) {
        case "sync": result = { settings, page: ui.page, craftTarget: ui.craftTarget, state: groups() }; break;
        case "resonate": result = await player.resonate(args[0] as number); break;
        case "craftItem": result = await player.craftItem(args[0] as string); break;
        case "setAccount": result = await player.setAccount(args[0] as player.AccountSession | null, args[1] as boolean); break;
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
  const syncedSettings = await syncSettings();
  return () => {
    unlisten(); unInterest(); stops.forEach((stop) => stop()); stopMembers(); stopEmote();
    memberStops.forEach((stop) => stop()); clearTimeout(motionTimer); clearTimeout(stateTimer); syncedSettings.stop();
  };
}
