import { emitTo, listen } from "@tauri-apps/api/event";
import { markRaw, nextTick, ref, watch } from "vue";
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
import { guideLink } from "../stores/guide";
import * as feedbackStore from "../stores/feedback";
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
    cheerOn: room.cheerOn.value, cheer: room.cheer.value, cheerDone: room.cheerDone.value, ddzMatchOn: room.ddzMatchOn.value,
    ddzWatchOn: room.ddzWatchOn.value }),
  publicRooms: () => room.publicRooms.value,
  pomodoro: () => pomodoroStore.pomodoro.value,
  todos: () => todoStore.todos.value,
  ddz: () => ({ table: ddzStore.ddz.value, live: ddzStore.ddzLive.value, liveBase: ddzStore.ddzLiveBase.value,
    liveState: ddzStore.ddzLiveState.value, queue: ddzStore.ddzQueue.value,
    waiting: ddzStore.ddzWaiting.value, retry: ddzStore.ddzRetry.value, tables: ddzStore.ddzTables.value,
    call: ddzStore.ddzCall.value, link: ddzStore.ddzLink.value, linkOff: ddzStore.ddzLinkOff.value,
    emotes: ddzStore.ddzEmotes.value, watch: ddzStore.ddzWatch.value, watchers: ddzStore.ddzWatchers.value,
    hall: player.ddzHallOn.value }),
  members: () => [...room.members.values()].map(({ id, uid, nick, character, plate, ddz, ddzMatch }) =>
    ({ id, uid, nick, character, plate, ddz, ddzMatch })),
};
type GroupKey = keyof typeof groupSources;
type Groups = { [K in GroupKey]: ReturnType<(typeof groupSources)[K]> };
const ALL_GROUPS = Object.keys(groupSources) as GroupKey[];
const WINDOW_GROUPS: Record<MirrorLabel, ReadonlySet<GroupKey>> = {
  panel: new Set(ALL_GROUPS),
  ddz: new Set(["ddz", "room", "members", "player", "economy", "collection", "checkins", "scratchCard", "counter", "publicRooms"]),
};
function groupsForWindow(target: MirrorLabel): Partial<Groups> {
  const out: Partial<Groups> = {};
  for (const key of WINDOW_GROUPS[target]) {
    (out as Record<string, unknown>)[key] = groupSources[key]();
  }
  return out;
}
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
    ddzStore.ddzLiveBase.value = s.ddz.liveBase;
    ddzStore.ddzLiveState.value = s.ddz.liveState ?? {};
    ddzStore.ddzQueue.value = s.ddz.queue;
    ddzStore.ddzWaiting.value = s.ddz.waiting;
    ddzStore.ddzRetry.value = s.ddz.retry;
    ddzStore.ddzTables.value = s.ddz.tables;
    ddzStore.ddzCall.value = s.ddz.call;
    ddzStore.ddzLink.value = s.ddz.link;
    ddzStore.ddzLinkOff.value = s.ddz.linkOff;
    ddzStore.ddzEmotes.value = s.ddz.emotes;
    ddzStore.ddzWatch.value = s.ddz.watch;
    ddzStore.ddzWatchers.value = s.ddz.watchers;
    player.ddzHallOn.value = !!s.ddz.hall;
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
    room.ddzWatchOn.value = s.room.ddzWatchOn;
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
 * `guide`: the panel's opening queue is still going (stores/guide.ts).
 */
interface Interest {
  from?: MirrorLabel; visible: boolean; live: boolean; motionIds?: string[]; seen?: boolean;
  guide?: { busy: boolean };
}

/** The desk owns network state; the mirror windows subscribe to independent slices while they are up. */
export async function initDesktop(): Promise<() => void> {
  if (!isTauri) return () => {};
  if (isMirrorWindow) {
    const target = windowLabel as MirrorLabel;
    const unState = await listen<Partial<Groups>>("desktop:state", ({ payload }) => applyGroups(payload), { target });
    const unMotion = await listen<{ members: Runtime[]; local: LocalPet }>("desktop:motion",
      ({ payload }) => applyRuntime(payload.members, payload.local), { target });
    const syncedSettings = await syncSettings();
    const initial = await requestDesktop<{ settings: Settings; page: typeof ui.page; craftTarget: string; state: Partial<Groups> }>("sync");
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
      return { from: target, visible, live: ui.page === "room", motionIds: visible ? motionIds.value : [],
        guide: { busy: guideLink.panelBusy } };
    };
    const stop = watch(interest, (payload) => { void emitTo("main", "desktop:interest", payload); }, { immediate: true, deep: true });
    return () => { unState(); unMotion(); stop(); stopInterest(); syncedSettings.stop(); };
  }

  /** Each mirror window's interest; a window not listed (or closed) wants nothing. */
  const subs = new Map<MirrorLabel, { visible: boolean; live: boolean; motionIds: string[] }>();
  const INACTIVE = Symbol("inactive");
  // A mirror starts tracking at its sync reply. Its first visible interest releases the accumulated changes.
  const awaitingVisible = new Set<MirrorLabel>();
  const tracking = { panel: ref(false), ddz: ref(false) };
  const liveRef = ref(false);
  let interested = new Set<string>();
  const pendingKeys: Record<MirrorLabel, Set<GroupKey>> = { panel: new Set(), ddz: new Set() };
  const dirty = new Map<string, Runtime>();
  const dirtyEdges = new Set<string>();
  let edgeQueue: Runtime[] = [];
  let edgeScheduled = false;
  let stopped = false;
  let motionTimer: ReturnType<typeof setTimeout> | undefined;
  let stateTimer: ReturnType<typeof setTimeout> | undefined;
  const targets = (key: "visible" | "live") => [...subs].filter(([, sub]) => sub[key]).map(([label]) => label);
  const isWanted = (key: GroupKey) => tracking.panel.value || (tracking.ddz.value && WINDOW_GROUPS.ddz.has(key));
  const publish = async (only?: MirrorLabel) => {
    if (!only) {
      clearTimeout(stateTimer);
      stateTimer = undefined;
    }
    const cache: Partial<Groups> = {};
    const sends: Promise<unknown>[] = [];
    for (const to of targets("visible")) {
      if ((only && to !== only) || awaitingVisible.has(to)) continue;
      const keys = pendingKeys[to];
      if (!keys.size) continue;
      const patch: Partial<Groups> = {};
      for (const key of keys) {
        if (!(key in cache)) (cache as Record<string, unknown>)[key] = groupSources[key]();
        (patch as Record<string, unknown>)[key] = cache[key];
      }
      keys.clear();
      sends.push(emitTo(to, "desktop:state", patch));
    }
    if (sends.length) await Promise.all(sends);
  };
  const stops = ALL_GROUPS.map((key) => watch(
    () => (isWanted(key) ? groupSources[key]() : INACTIVE),
    (value, old) => {
      if (value === INACTIVE || old === INACTIVE) return;
      let queued = false;
      for (const label of ["panel", "ddz"] as const) {
        if (!tracking[label].value || !WINDOW_GROUPS[label].has(key)) continue;
        pendingKeys[label].add(key);
        if (subs.get(label)?.visible && !awaitingVisible.has(label)) queued = true;
      }
      if (queued) stateTimer ??= setTimeout(() => { void publish(); }, 50);
    },
    { deep: true },
  ));
  function sendMotion() {
    clearTimeout(motionTimer);
    motionTimer = undefined;
    edgeScheduled = false;
    if (stopped) return;
    const to = targets("live");
    if (!to.length) {
      dirty.clear();
      dirtyEdges.clear();
      edgeQueue = [];
      return;
    }
    const updates = edgeQueue.length ? [...edgeQueue, ...dirty.values()] : [...dirty.values()];
    edgeQueue = [];
    dirty.clear();
    dirtyEdges.clear();
    const message = { members: updates, local: { emote: room.localPet.emote, win: room.localPet.win } };
    for (const label of to) void emitTo(label, "desktop:motion", message);
  }
  /** Changes to one member merge until the next message; one frame's worth goes out together. */
  const queue = (update: Runtime, edge = false) => {
    if (edge) {
      if (dirtyEdges.has(update.id)) {
        const prev = dirty.get(update.id);
        if (prev) edgeQueue.push(prev);
        dirty.set(update.id, update);
      } else {
        dirty.set(update.id, { ...dirty.get(update.id), ...update });
        dirtyEdges.add(update.id);
      }
      if (!edgeScheduled) {
        edgeScheduled = true;
        queueMicrotask(() => { if (edgeScheduled) sendMotion(); });
      }
      return;
    }
    dirty.set(update.id, { ...dirty.get(update.id), ...update });
    motionTimer ??= setTimeout(sendMotion, 16);
  };
  const memberStops = new Map<string, () => void>();
  const stopMembers = watch(() => (liveRef.value ? [...room.members.keys()] : []), (ids) => {
    for (const [id, stop] of memberStops) if (!ids.includes(id)) { stop(); memberStops.delete(id); dirty.delete(id); dirtyEdges.delete(id); }
    for (const id of ids) if (!memberStops.has(id)) {
      memberStops.set(id, watch(() => {
        const member = room.members.get(id);
        return member ? runtime(member) : null;
      }, (value) => {
        if (value) queue(value);
        else { dirty.delete(id); dirtyEdges.delete(id); }
      }, { deep: true, immediate: true }));
    }
  });
  // Poses stay out of the reactive graph (net/MotionFrames.ts), so they are forwarded as they arrive.
  const stopMotion = remoteMotion.onUpdate((id, pose, edge) => {
    if (!liveRef.value || !interested.has(id)) return;
    // Every press and release reaches the panel's 70ms hold; edges within one microtask coalesce into one IPC.
    queue({ id, motion: { ...pose } }, edge);
  });
  const stopEmote = watch(() => (liveRef.value ? [room.localPet.emote, room.localPet.win] : null), () => {
    if (liveRef.value) motionTimer ??= setTimeout(sendMotion, 50);
  }, { deep: true });
  async function setInterest({ from = "panel", ...payload }: Interest) {
    const opening = payload.visible && !subs.get(from)?.visible;
    const firstVisible = payload.visible && awaitingVisible.delete(from);
    const live = payload.visible && payload.live;
    subs.set(from, { visible: payload.visible, live, motionIds: live ? payload.motionIds ?? [...room.members.keys()] : [] });
    tracking[from].value = payload.visible || awaitingVisible.has(from);
    if (!tracking[from].value) pendingKeys[from].clear();
    if (from === "ddz") ui.ddzSeen = payload.visible && !!payload.seen;
    // The panel's queue counts while it is hidden too: what is left of it comes up with the panel.
    if (from === "panel") {
      guideLink.panelVisible = payload.visible;
      guideLink.panelBusy = !!payload.guide?.busy;
    }
    const before = interested;
    interested = new Set([...subs.values()].flatMap((sub) => sub.motionIds));
    // The room socket subscribes for the mirror windows' pets as well as the desk's own.
    room.setPanelMotionInterest([...interested]);
    liveRef.value = [...subs.values()].some((sub) => sub.live);
    // A pet a window starts drawing begins from the pose held now, whenever the next update comes.
    for (const id of interested) {
      const member = before.has(id) ? undefined : room.members.get(id);
      if (member) queue({ id, motion: { ...member.motion } });
    }
    if (!liveRef.value) {
      dirty.clear(); dirtyEdges.clear(); edgeQueue = []; edgeScheduled = false;
      clearTimeout(motionTimer);
      motionTimer = undefined;
    }
    if (opening || firstVisible) {
      if (!firstVisible) for (const key of WINDOW_GROUPS[from]) pendingKeys[from].add(key);
      await nextTick();
      await publish(from);
    }
  }
  const unInterest = await listen<Interest>("desktop:interest", ({ payload }) => setInterest(payload), { target: "main" });
  // The table's window closed (src-tauri/src/lib.rs): it wants nothing more, and the game goes on without it.
  const unDdzClosed = await listen("ddz:closed", () => {
    awaitingVisible.delete("ddz");
    void setInterest({ from: "ddz", visible: false, live: false });
    ddzStore.noteDdzWindowClosed();
  }, { target: "main" });
  // The todos' window (desktop/todoBridge.ts) gets the list on every change, also while it is hidden: it is small.
  const stopTodos = watch(() => todoStore.todos.value, (list) => { void emitTo("todo", "desktop:todos", list); });
  const unlisten = await listen<DesktopRequest>("desktop:request", async ({ payload: { id, action, args, from = "panel" } }) => {
    try {
      let result: unknown;
      switch (action) {
        case "sync": {
          const target = from === "ddz" ? "ddz" : "panel";
          awaitingVisible.add(target);
          tracking[target].value = true;
          // Establish watcher baselines before taking the snapshot that covers all changes so far.
          await nextTick();
          pendingKeys[target].clear();
          result = { settings, page: ui.page, craftTarget: ui.craftTarget, state: groupsForWindow(target) };
          break;
        }
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
        case "loadDdzLobby": result = await player.loadDdzLobby((args[0] as string | null | undefined) ?? undefined); break;
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
        case "feedback": result = await feedbackStore.sendFeedback(args[0] as feedbackStore.FeedbackDraft); break;
      }
      if (action !== "sync") {
        await nextTick();
        await publish();
      }
      await emitTo(from, `desktop:reply:${id}`, { result });
    } catch (e) {
      await emitTo(from, `desktop:reply:${id}`, { error: e instanceof Error ? e.message : String(e) });
    }
  }, { target: "main" });
  const syncedSettings = await syncSettings();
  return () => {
    stopped = true;
    edgeScheduled = false;
    unlisten(); unInterest(); unDdzClosed(); stops.forEach((stop) => stop()); stopMembers(); stopEmote(); stopMotion(); stopTodos();
    room.setPanelMotionInterest([]);
    memberStops.forEach((stop) => stop()); clearTimeout(motionTimer); clearTimeout(stateTimer); syncedSettings.stop();
  };
}
