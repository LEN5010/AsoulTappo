import { emitTo, listen } from "@tauri-apps/api/event";
import { markRaw, ref, watch } from "vue";
import { isPanelWindow, isTauri } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import * as player from "../stores/player";
import * as room from "../stores/room";
import * as parkStore from "../stores/park";
import { restingMotion, type PetMotion } from "../net/protocol";
import { remoteMotion } from "../net/MotionFrames";
import { windowVisible } from "../stores/activity";
import { counter } from "../stores/counter";
import { tidyRemotes } from "../stores/desk";
import { ui } from "../stores/ui";
import { requestDesktop, type DesktopRequest } from "./transport";

const groupSources = {
  player: () => ({ status: player.status.value, online: player.online.value, error: player.error.value }),
  collection: () => player.collection,
  checkins: () => player.checkins.value,
  scratchCard: () => player.scratchCard.value,
  park: () => parkStore.park.value,
  freshItems: () => [...player.freshItems], counter: () => ({ ...counter }),
  room: () => ({ conn: room.conn.value, roomId: room.roomId.value, youId: room.youId.value, lastError: room.lastError.value,
    info: room.roomInfo.value, duel: room.duel.value, profileOn: room.profileOn.value,
    cheerOn: room.cheerOn.value, cheer: room.cheer.value, cheerDone: room.cheerDone.value }),
  publicRooms: () => room.publicRooms.value,
  members: () => [...room.members.values()].map(({ id, uid, nick, character, plate }) =>
    ({ id, uid, nick, character, plate })),
};
function groups() {
  return { player: groupSources.player(), collection: groupSources.collection(), checkins: groupSources.checkins(),
    scratchCard: groupSources.scratchCard(), park: groupSources.park(), freshItems: groupSources.freshItems(), counter: groupSources.counter(), room: groupSources.room(),
    publicRooms: groupSources.publicRooms(), members: groupSources.members() };
}
const groupsFor = <K extends keyof Groups>(key: K) => groupSources[key]();
type Groups = ReturnType<typeof groups>;
/**
 * What changed about one member's pet since the last message. Taps, emote, combo and win go to the panel for
 * every member (its member list counts taps); the pose only for the pets the panel is drawing.
 */
type Runtime = { id: string; motion?: PetMotion } & Partial<Pick<room.RemoteMember, "taps" | "pulse" | "emote" | "combo" | "win">>;
const runtime = (m: room.RemoteMember): Runtime => ({
  id: m.id, taps: m.taps, pulse: m.pulse, emote: m.emote, combo: m.combo, win: m.win,
});
type LocalPet = typeof room.localPet;
const pendingRuntime = new Map<string, Runtime>();
function applyGroups(s: Partial<Groups>) {
  if (s.player) {
    player.status.value = s.player.status;
    player.online.value = s.player.online;
    player.error.value = s.player.error;
  }
  if (s.collection) Object.assign(player.collection, s.collection);
  if (s.checkins !== undefined) player.checkins.value = s.checkins;
  if (s.scratchCard !== undefined) player.scratchCard.value = s.scratchCard;
  if (s.park !== undefined) parkStore.park.value = s.park;
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
    room.roomInfo.value = s.room.info;
    room.duel.value = s.room.duel;
    room.profileOn.value = s.room.profileOn;
    room.cheerOn.value = s.room.cheerOn;
    room.cheer.value = s.room.cheer;
    room.cheerDone.value = s.room.cheerDone;
  }
  if (s.publicRooms !== undefined) room.publicRooms.value = s.publicRooms;
  if (s.members) {
    const ids = new Set(s.members.map((m) => m.id));
    for (const id of room.members.keys()) if (!ids.has(id)) {
      room.members.delete(id);
      pendingRuntime.delete(id);
      remoteMotion.remove(id);
    }
    for (const m of s.members) {
      const existing = room.members.get(m.id);
      if (existing) Object.assign(existing, m);
      else room.members.set(m.id, { ...m, taps: 0, pulse: 0, emote: null, combo: null, win: null, motion: markRaw(restingMotion()) });
      // What its pet was doing may have arrived ahead of the member itself.
      const early = pendingRuntime.get(m.id);
      if (early) { pendingRuntime.delete(m.id); applyMember(early); }
    }
  }
}
function applyMember({ motion, ...rest }: Runtime): boolean {
  const member = room.members.get(rest.id);
  if (!member) return false;
  Object.assign(member, rest);
  if (motion) {
    Object.assign(member.motion, motion);
    remoteMotion.update(rest.id, motion);
  }
  return true;
}
function applyRuntime(updates: Runtime[], local: LocalPet) {
  for (const update of updates) {
    if (!applyMember(update)) pendingRuntime.set(update.id, { ...pendingRuntime.get(update.id), ...update });
  }
  room.localPet.emote = local.emote;
  room.localPet.win = local.win;
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
  const stop = watch(() => ({ ...settings, favorites: [...settings.favorites], showcase: [...settings.showcase] }), (value, old) => {
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
    const unMotion = await listen<{ members: Runtime[]; local: LocalPet }>("desktop:motion",
      ({ payload }) => applyRuntime(payload.members, payload.local), { target: "panel" });
    const syncedSettings = await syncSettings();
    const initial = await requestDesktop<{ settings: Settings; page: typeof ui.page; craftTarget: string; state: Groups }>("sync");
    syncedSettings.apply(initial.settings);
    applyGroups(initial.state);
    ui.page = initial.page;
    ui.craftTarget = initial.craftTarget;
    const motionIds = ref<string[]>([]);
    const stopInterest = remoteMotion.onInterest((ids) => { motionIds.value = ids; });
    // The pets the room page is drawing: the desk subscribes to their movement and passes it on.
    const stop = watch(() => [ui.panelOpen && !ui.panelMinimized && windowVisible.value, ui.page === "room", motionIds.value] as const,
      ([visible, live, ids]) => { void emitTo("main", "desktop:interest", { visible, live, motionIds: visible ? ids : [] }); }, { immediate: true });
    return () => { unState(); unMotion(); stop(); stopInterest(); syncedSettings.stop(); };
  }

  const visibleRef = ref(false);
  const liveRef = ref(false);
  let interested = new Set<string>();
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
    clearTimeout(motionTimer);
    motionTimer = undefined;
    if (!visible || !live) return;
    const updates = [...dirty.values()];
    dirty.clear();
    void emitTo("panel", "desktop:motion", { members: updates,
      local: { emote: room.localPet.emote, win: room.localPet.win } });
  }
  /** Changes to one member merge until the next message; one frame's worth goes out together. */
  const queue = (update: Runtime) => {
    dirty.set(update.id, { ...dirty.get(update.id), ...update });
    motionTimer ??= setTimeout(sendMotion, 16);
  };
  const memberStops = new Map<string, () => void>();
  const stopMembers = watch(() => liveRef.value ? [...room.members.keys()] : [], (ids) => {
    for (const [id, stop] of memberStops) if (!ids.includes(id)) { stop(); memberStops.delete(id); dirty.delete(id); }
    for (const id of ids) if (!memberStops.has(id)) {
      memberStops.set(id, watch(() => {
        const member = room.members.get(id);
        return member ? runtime(member) : null;
      }, (value) => {
        if (value) queue(value);
        else dirty.delete(id);
      }, { deep: true, immediate: true, flush: "sync" }));
    }
  }, { flush: "sync" });
  // Poses stay out of the reactive graph (net/MotionFrames.ts), so they are forwarded as they arrive.
  const stopMotion = remoteMotion.onUpdate((id, pose, edge) => {
    if (!live || !interested.has(id)) return;
    queue({ id, motion: pose });
    // Every press and release reaches the panel's 70ms hold, including both edges within one frame.
    if (edge) sendMotion();
  });
  const stopEmote = watch(() => liveRef.value ? [room.localPet.emote, room.localPet.win] : null, () => {
    if (liveRef.value) motionTimer ??= setTimeout(sendMotion, 50);
  }, { deep: true });
  const unInterest = await listen<{ visible: boolean; live: boolean; motionIds?: string[] }>("desktop:interest", async ({ payload }) => {
    const opening = payload.visible && !visible;
    visible = payload.visible;
    live = visible && payload.live;
    const before = interested;
    interested = new Set(live ? payload.motionIds ?? room.members.keys() : []);
    // The room socket subscribes for the panel's pets as well as the desk's own.
    room.setPanelMotionInterest([...interested]);
    visibleRef.value = visible;
    liveRef.value = live;
    // A pet the panel starts drawing begins from the pose held now, whenever the next update comes.
    for (const id of interested) {
      const member = before.has(id) ? undefined : room.members.get(id);
      if (member) queue({ id, motion: { ...member.motion } });
    }
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
        case "checkin": result = await player.checkin(); break;
        case "claimUpdateRewards": result = await player.claimUpdateRewards(); break;
        case "loadCheckins": await player.loadCheckins(); break;
        case "loadScratch": await player.loadScratch(); break;
        case "buyScratch": result = await player.buyScratch(); break;
        case "revealScratch": result = await player.revealScratch(args[0] as number); break;
        case "setAccount": result = await player.setAccount(args[0] as player.AccountSession | null, args[1] as boolean); break;
        case "sendEmote": result = room.sendEmote(args[0] as string, args[1] as number); break;
        case "createRoom": result = await room.createRoom(); break;
        case "joinRoom": room.joinRoom(args[0] as string); break;
        case "leaveRoom": room.leaveRoom(); break;
        case "setRoomPublic": room.setRoomPublic(args[0] as boolean); break;
        case "kickMember": room.kickMember(args[0] as string); break;
        case "loadPublicRooms": await room.loadPublicRooms(); break;
        case "inviteDuel": room.inviteDuel(args[0] as string, args[1] as number); break;
        case "loadProfile": result = await room.loadProfile(args[0] as string); break;
        case "loadBoard": result = await player.loadBoard(); break;
        case "loadBoardProfile": result = await player.loadBoardProfile(args[0] as string); break;
        case "park": result = await parkStore.parkRequest(args[0] as parkStore.ParkMethod, args[1] as string, args[2]); break;
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
    unlisten(); unInterest(); stops.forEach((stop) => stop()); stopMembers(); stopEmote(); stopMotion();
    room.setPanelMotionInterest([]);
    memberStops.forEach((stop) => stop()); clearTimeout(motionTimer); clearTimeout(stateTimer); syncedSettings.stop();
  };
}
