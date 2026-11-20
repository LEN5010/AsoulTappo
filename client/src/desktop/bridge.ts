import { emitTo, listen } from "@tauri-apps/api/event";
import { markRaw, ref, watch } from "vue";
import { isMirrorWindow, isPanelWindow, isTauri, windowLabel } from "../composables/tauri";
import { settings, type Settings } from "../stores/settings";
import { syncSettings } from "./settingsSync";
import * as player from "../stores/player";
import * as room from "../stores/room";
import * as parkStore from "../stores/park";
import * as pomodoroStore from "../stores/pomodoro";
import * as nudgeStore from "../stores/nudge";
import type { Reminder } from "../reminders";
import * as todoStore from "../stores/todo";
import * as ddzStore from "../stores/ddz";
import { economy, setEconomy } from "../stores/economy";
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
  economy: () => economy.value,
  freshItems: () => [...player.freshItems], counter: () => ({ ...counter }),
  room: () => ({ conn: room.conn.value, roomId: room.roomId.value, youId: room.youId.value, lastError: room.lastError.value,
    info: room.roomInfo.value, duel: room.duel.value, profileOn: room.profileOn.value, nameOn: room.nameOn.value,
    cheerOn: room.cheerOn.value, cheer: room.cheer.value, cheerDone: room.cheerDone.value, ddzMatchOn: room.ddzMatchOn.value }),
  publicRooms: () => room.publicRooms.value,
  pomodoro: () => pomodoroStore.pomodoro.value,
  todos: () => todoStore.todos.value,
  ddz: () => ({ table: ddzStore.ddz.value, live: ddzStore.ddzLive.value, queue: ddzStore.ddzQueue.value,
    waiting: ddzStore.ddzWaiting.value, retry: ddzStore.ddzRetry.value, tables: ddzStore.ddzTables.value,
    call: ddzStore.ddzCall.value, link: ddzStore.ddzLink.value, linkOff: ddzStore.ddzLinkOff.value,
    emotes: ddzStore.ddzEmotes.value }),
  members: () => [...room.members.values()].map(({ id, uid, nick, character, plate, ddz, ddzMatch }) =>
    ({ id, uid, nick, character, plate, ddz, ddzMatch })),
};
function groups() {
  return { player: groupSources.player(), collection: groupSources.collection(), checkins: groupSources.checkins(),
    scratchCard: groupSources.scratchCard(), park: groupSources.park(), economy: groupSources.economy(), freshItems: groupSources.freshItems(), counter: groupSources.counter(), room: groupSources.room(),
    publicRooms: groupSources.publicRooms(), pomodoro: groupSources.pomodoro(), todos: groupSources.todos(), ddz: groupSources.ddz(),
    members: groupSources.members() };
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
  if (s.pomodoro !== undefined) pomodoroStore.pomodoro.value = s.pomodoro;
  if (s.todos !== undefined) todoStore.todos.value = s.todos;
  if (s.ddz) {
    ddzStore.ddz.value = s.ddz.table;
    ddzStore.ddzLive.value = s.ddz.live;
    ddzStore.ddzQueue.value = s.ddz.queue;
    ddzStore.ddzWaiting.value = s.ddz.waiting;
    ddzStore.ddzRetry.value = s.ddz.retry;
    ddzStore.ddzTables.value = s.ddz.tables;
    ddzStore.ddzCall.value = s.ddz.call;
    ddzStore.ddzLink.value = s.ddz.link;
    ddzStore.ddzLinkOff.value = s.ddz.linkOff;
    ddzStore.ddzEmotes.value = s.ddz.emotes;
  }
  if (s.economy) setEconomy(s.economy);
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
    room.nameOn.value = s.room.nameOn;
    room.cheerOn.value = s.room.cheerOn;
    room.cheer.value = s.room.cheer;
    room.cheerDone.value = s.room.cheerDone;
    room.ddzMatchOn.value = s.room.ddzMatchOn;
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
      else room.members.set(m.id, { ...m, taps: 0, pulse: 0, emote: null, combo: null, win: null, sip: 0, motion: markRaw(restingMotion()) });
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

/** The windows that mirror the desk: the panel and the dou dizhu table's window. */
type MirrorLabel = "panel" | "ddz";
/**
 * What a mirror window wants from the desk. `visible`: the state, `live`: its pets' movement (only of `motionIds`).
 * `seen`: the table's window is on screen, not minimized (it gets the state while minimized: the game goes on).
 */
interface Interest { from?: MirrorLabel; visible: boolean; live: boolean; motionIds?: string[]; seen?: boolean }

/** The desk owns network state; the mirror windows subscribe to independent slices while they are up. */
export async function initDesktop(): Promise<() => void> {
  if (!isTauri) return () => {};
  if (isMirrorWindow) {
    const target = windowLabel as MirrorLabel;
    const unState = await listen<Partial<Groups>>("desktop:state", ({ payload }) => applyGroups(payload), { target });
    const unMotion = await listen<{ members: Runtime[]; local: LocalPet }>("desktop:motion",
      ({ payload }) => applyRuntime(payload.members, payload.local), { target });
    const syncedSettings = await syncSettings();
    const initial = await requestDesktop<{ settings: Settings; page: typeof ui.page; craftTarget: string; state: Groups }>("sync");
    syncedSettings.apply(initial.settings);
    applyGroups(initial.state);
    if (isPanelWindow) {
      ui.page = initial.page;
      ui.craftTarget = initial.craftTarget;
    }
    const motionIds = ref<string[]>([]);
    const stopInterest = remoteMotion.onInterest((ids) => { motionIds.value = ids; });
    // The pets the room page (or the table) is drawing: the desk subscribes to their movement and passes it on.
    const interest = (): Interest => {
      if (target === "ddz") {
        const seen = ui.ddzSeen && windowVisible.value;
        return { from: target, visible: true, live: seen, seen, motionIds: seen ? motionIds.value : [] };
      }
      const visible = ui.panelOpen && !ui.panelMinimized && windowVisible.value;
      return { from: target, visible, live: ui.page === "room", motionIds: visible ? motionIds.value : [] };
    };
    const stop = watch(interest, (payload) => { void emitTo("main", "desktop:interest", payload); }, { immediate: true, deep: true });
    return () => { unState(); unMotion(); stop(); stopInterest(); syncedSettings.stop(); };
  }

  /** Each mirror window's interest; a window not listed (or closed) wants nothing. */
  const subs = new Map<MirrorLabel, { visible: boolean; live: boolean; motionIds: string[] }>();
  const visibleRef = ref(false);
  const liveRef = ref(false);
  let interested = new Set<string>();
  let pending: Partial<Groups> = {};
  const dirty = new Map<string, Runtime>();
  let motionTimer: ReturnType<typeof setTimeout> | undefined;
  let stateTimer: ReturnType<typeof setTimeout> | undefined;
  const targets = (key: "visible" | "live") => [...subs].filter(([, sub]) => sub[key]).map(([label]) => label);
  const publish = async () => {
    clearTimeout(stateTimer);
    stateTimer = undefined;
    const patch = pending;
    pending = {};
    if (Object.keys(patch).length) await Promise.all(targets("visible").map((to) => emitTo(to, "desktop:state", patch)));
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
    const to = targets("live");
    if (!to.length) return;
    const updates = [...dirty.values()];
    dirty.clear();
    const message = { members: updates, local: { emote: room.localPet.emote, win: room.localPet.win } };
    for (const label of to) void emitTo(label, "desktop:motion", message);
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
    if (!liveRef.value || !interested.has(id)) return;
    queue({ id, motion: pose });
    // Every press and release reaches the panel's 70ms hold, including both edges within one frame.
    if (edge) sendMotion();
  });
  const stopEmote = watch(() => liveRef.value ? [room.localPet.emote, room.localPet.win] : null, () => {
    if (liveRef.value) motionTimer ??= setTimeout(sendMotion, 50);
  }, { deep: true });
  async function setInterest({ from = "panel", ...payload }: Interest) {
    const opening = payload.visible && !subs.get(from)?.visible;
    const live = payload.visible && payload.live;
    subs.set(from, { visible: payload.visible, live, motionIds: live ? payload.motionIds ?? [...room.members.keys()] : [] });
    if (from === "ddz") ui.ddzSeen = payload.visible && !!payload.seen;
    const before = interested;
    interested = new Set([...subs.values()].flatMap((sub) => sub.motionIds));
    // The room socket subscribes for the mirror windows' pets as well as the desk's own.
    room.setPanelMotionInterest([...interested]);
    visibleRef.value = [...subs.values()].some((sub) => sub.visible);
    liveRef.value = [...subs.values()].some((sub) => sub.live);
    // A pet a window starts drawing begins from the pose held now, whenever the next update comes.
    for (const id of interested) {
      const member = before.has(id) ? undefined : room.members.get(id);
      if (member) queue({ id, motion: { ...member.motion } });
    }
    if (!visibleRef.value) {
      pending = {}; dirty.clear(); clearTimeout(stateTimer); clearTimeout(motionTimer);
      stateTimer = motionTimer = undefined;
    } else if (opening) {
      // The window that just came up gets everything; the others only what changes.
      await emitTo(from, "desktop:state", groups());
    }
  }
  const unInterest = await listen<Interest>("desktop:interest", ({ payload }) => setInterest(payload), { target: "main" });
  // The table's window closed (src-tauri/src/lib.rs): it wants nothing more, and the game goes on without it.
  const unDdzClosed = await listen("ddz:closed", () => {
    void setInterest({ from: "ddz", visible: false, live: false });
    ddzStore.noteDdzWindowClosed();
  }, { target: "main" });
  // The todos' window (desktop/todoBridge.ts) gets the list on every change, also while it is hidden: it is small.
  const stopTodos = watch(() => todoStore.todos.value, (list) => { void emitTo("todo", "desktop:todos", list); }, { flush: "sync" });
  const unlisten = await listen<DesktopRequest>("desktop:request", async ({ payload: { id, action, args, from = "panel" } }) => {
    try {
      let result: unknown;
      switch (action) {
        case "sync": result = { settings, page: ui.page, craftTarget: ui.craftTarget, state: groups() }; break;
        case "resonate": result = await player.resonate(args[0] as number, (args[1] as string | null) ?? undefined); break;
        case "craftItem": result = await player.craftItem(args[0] as string); break;
        case "loadHistory": result = await player.loadHistory((args[0] as number | null) ?? undefined); break;
        case "checkin": result = await player.checkin(); break;
        case "claimUpdateRewards": result = await player.claimUpdateRewards(); break;
        case "loadCheckins": await player.loadCheckins(); break;
        case "loadScratch": await player.loadScratch(); break;
        case "buyScratch": result = await player.buyScratch(); break;
        case "revealScratch": result = await player.revealScratch(args[0] as number); break;
        case "setAccount": result = await player.setAccount(args[0] as player.AccountSession | null, args[1] as boolean); break;
        case "sendEmote": result = room.sendEmote(args[0] as string, args[1] as number, (args[2] as boolean | null) ?? true); break;
        case "createRoom": result = await room.createRoom(); break;
        case "joinRoom": room.joinRoom(args[0] as string); break;
        case "leaveRoom": room.leaveRoom(); break;
        case "setRoomPublic": room.setRoomPublic(args[0] as boolean); break;
        case "setRoomName": room.setRoomName(args[0] as string); break;
        case "kickMember": room.kickMember(args[0] as string); break;
        case "loadPublicRooms": await room.loadPublicRooms(); break;
        case "inviteDuel": room.inviteDuel(args[0] as string, args[1] as number); break;
        case "loadProfile": result = await room.loadProfile(args[0] as string); break;
        case "loadBoard": result = await player.loadBoard(); break;
        case "loadDdzLobby": result = await player.loadDdzLobby(); break;
        case "loadBoardProfile": result = await player.loadBoardProfile(args[0] as string); break;
        case "loadEconomy": await player.loadEconomy(args[0] as string); break;
        case "park": result = await parkStore.parkRequest(args[0] as parkStore.ParkMethod, args[1] as string, args[2]); break;
        case "tidyRemotes": tidyRemotes(); break;
        case "beginPomodoro": pomodoroStore.beginPomodoro(); break;
        case "endPomodoro": pomodoroStore.endPomodoro(); break;
        case "tryReminder": nudgeStore.tryReminder(args[0] as Reminder); break;
        case "todo": todoStore.todoRequest(args[0] as todoStore.TodoMethod, args[1]); break;
        case "todoSync": result = { settings, todos: todoStore.todos.value }; break;
        case "raceSync": result = { settings }; break;
        case "ddz": ddzStore.ddzRequest(args[0] as ddzStore.DdzOp, ...args.slice(1)); break;
      }
      await publish();
      await emitTo(from, `desktop:reply:${id}`, { result });
    } catch (e) {
      await emitTo(from, `desktop:reply:${id}`, { error: e instanceof Error ? e.message : String(e) });
    }
  }, { target: "main" });
  const syncedSettings = await syncSettings();
  return () => {
    unlisten(); unInterest(); unDdzClosed(); stops.forEach((stop) => stop()); stopMembers(); stopEmote(); stopMotion(); stopTodos();
    room.setPanelMotionInterest([]);
    memberStops.forEach((stop) => stop()); clearTimeout(motionTimer); clearTimeout(stateTimer); syncedSettings.stop();
  };
}
