import { computed, markRaw, reactive, ref, watch } from "vue";
import { RoomClient, type ConnState, type RoomEvents } from "../net/RoomClient";
import { TapBatcher } from "../net/TapBatcher";
import { remoteMotion } from "../net/MotionFrames";
import { noteActivity } from "./activity";
import { MotionSender } from "../net/MotionSender";
import {
  restingMotion, toHttpBase, type DuelMessage, type Hand, type Member, type PetMotion, type ProfilePatch, type PublicRoom,
  type RoomInfo,
} from "../net/protocol";
import { ownsEmote } from "../items";
import { getEmote, manifest, memberOf } from "../manifest";
import { faceKey, faceOf } from "../scratch";
import { EmotePlayer, SEND_INTERVAL_MS, type EmoteFrame } from "../pet/EmotePlayer";
import { TapCombo, type ComboFrame } from "../pet/TapCombo";
import { settings } from "./settings";
import { activeAccount, account, collection, token, saveCode, reloadStatus, setAccount, status } from "./player";
import { Api, authHeaders } from "../net/api";
import { isPanelWindow, writeLog } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";

export interface RemoteMember extends Member {
  /** increments on every tap batch -> short keyboard bounce */
  pulse: number;
  emote: EmoteFrame | null;
  combo: ComboFrame | null;
  /** Shards a scratch card or a duel just paid this member, shown over the pet for a moment. */
  win: ComboFrame | null;
  motion: PetMotion;
}

/** This client's rock-paper-scissors duel, from the invite to a short look at how it ended. */
export interface DuelState {
  id: string;
  /** The other member, named as when the invite came. */
  other: { id: string; nick: string; character: string };
  /** This client sent the invite. */
  sent: boolean;
  bet: number;
  prize: number;
  phase: "invite" | "throw" | "result" | "over";
  /** The invite was answered; waiting for the bets to be taken. */
  answered: boolean;
  round: number;
  /** The current countdown: its length and its end in local ms. */
  sec: number;
  until: number;
  /** Hand thrown this round. */
  hand: Hand | null;
  /** Hands of the last draw, or the final ones. */
  shown: { mine: Hand | null; theirs: Hand | null } | null;
  won: boolean;
  /** Why it ended without a winner (duel_over). */
  reason: string;
}

/** How long a scratch card win stays over a pet. */
const WIN_MS = 3600;
/** How long the outcome of a duel stays beside the own pet. */
export const DUEL_END_MS = 4000;
/** Rock-paper-scissors numbers, the same manifest the server reads. */
export const duelConfig = manifest.economy.duel ?? null;

export const conn = ref<ConnState>("idle");
export const roomId = ref("");
export const youId = ref("");
export const lastError = ref("");
export const members = reactive(new Map<string, RemoteMember>());
const players = new Map<string, {
  emote: EmotePlayer; combo: TapCombo; win: TapCombo;
}>();

export const others = computed(() => [...members.values()].filter((m) => m.id !== youId.value));
export const me = computed(() => members.get(youId.value) ?? null);
export const inRoom = computed(() => conn.value === "open" && !!youId.value);
/** Host and public flag of the joined room; null before `joined` and from servers without them. */
export const roomInfo = ref<RoomInfo | null>(null);
export const isHost = computed(() => inRoom.value && !!roomInfo.value?.host && roomInfo.value.host === youId.value);
/**
 * Public rooms of the current server; null until loaded, and when the server has no list. "signin" when the server
 * shows the list only to a signed-in main-site account and none is signed in.
 */
export const publicRooms = ref<PublicRoom[] | "signin" | null>(null);

/** A partner's name as shown: their pet's member name while nicknames are hidden. */
export const shownNick = (m: Pick<Member, "nick" | "character">) => (settings.hideNicks ? memberOf(m.character) : m.nick);

/** Stable key of a member for remembering where their pet stands on the desk. */
export const memberKey = (m: Member) => m.uid ?? `nick:${m.nick}`;

function add(m: Member): void {
  members.set(m.id, {
    ...m, pulse: 0, emote: null, combo: null, win: null, motion: markRaw(m.motion ? { ...m.motion } : restingMotion()),
  });
  const rm = members.get(m.id)!;
  remoteMotion.update(m.id, rm.motion);
  players.set(m.id, {
    emote: new EmotePlayer((f) => (rm.emote = f), () => settings.emoteHoldMs),
    combo: new TapCombo((f) => (rm.combo = f)),
    win: new TapCombo((f) => (rm.win = f), WIN_MS),
  });
}

function remove(id: string): void {
  const p = players.get(id);
  p?.emote.clear();
  p?.combo.stop();
  p?.win.stop();
  remoteMotion.remove(id);
  players.delete(id);
  members.delete(id);
}

function clearMembers(): void {
  for (const id of [...members.keys()]) remove(id);
}

/** `rate_limited` errors since the last log line; counted instead of logged one by one. */
let rateLimited = 0;

const events: RoomEvents = {
  onConnState(s) {
    writeLog("room", rateLimited ? `${s} (${rateLimited} rate_limited before)` : s);
    rateLimited = 0;
    conn.value = s;
    if (s !== "open") {
      motionSender.clear();
      // Membership is rebuilt from `joined` after (re)connect; a duel ends with the connection it was played on.
      clearMembers();
      youId.value = "";
      roomInfo.value = null;
      endDuel();
      endPokes();
    }
  },
  onJoined(room, you, list, features) {
    roomId.value = room;
    youId.value = you;
    pokeOn.value = features.includes("poke");
    lastError.value = "";
    clearMembers();
    list.forEach(add);
    writeLog("room", `joined, ${list.length} member(s)`);
  },
  onRoomInfo(info) {
    roomInfo.value = info;
  },
  onMemberJoined: add,
  onMemberLeft: remove,
  onTap(id, count, total) {
    const m = members.get(id);
    if (!m) return;
    m.taps = total;
    if (id === youId.value) return; // local pet already reacted instantly
    noteActivity();
    m.pulse += 1;
    players.get(id)?.combo.add(count);
  },
  onEmote(id, name) {
    if (id === youId.value) return; // shown locally on send
    if (!getEmote(name)) return;
    noteActivity();
    players.get(id)?.emote.play(name);
  },
  onScratch(id, shards) {
    // The shards go up over the winner's pet, and 阿草 takes it as badly as it does at the stall.
    const face = faceKey(faceOf({ kind: "shards", amount: shards, at: [] }));
    noteActivity();
    if (id === youId.value) {
      localWin.add(shards);
      if (face) localPlayer.play(face);
      return;
    }
    const p = players.get(id);
    p?.win.add(shards);
    if (face) p?.emote.play(face);
  },
  onMotion(id, pose) {
    const member = members.get(id);
    if (member && id !== youId.value) {
      noteActivity();
      // Kept for the panel's mirror (desktop/bridge.ts) and never watched: pets are drawn from remoteMotion.
      Object.assign(member.motion, pose);
      remoteMotion.update(id, pose);
    }
  },
  onPoke(from, to, quiet) {
    noteActivity();
    if (to !== youId.value) {
      const m = members.get(to);
      if (m) m.pulse += 1;
      return;
    }
    localPet.pulse += 1;
    const m = members.get(from);
    if (!quiet && m && from !== youId.value) showPoked(from, shownNick(m));
  },
  onDuel(msg) {
    noteActivity();
    onDuelMessage(msg);
  },
  onState(u) {
    const m = members.get(u.id);
    if (!m) return;
    m.character = u.character;
    m.nick = u.nick;
    m.plate = u.plate ?? null;
  },
  onError(code, message) {
    // A late answer or hand for a duel that already ended: nothing to tell.
    if (code === "duel_gone") return;
    if (code === "rate_limited") {
      rateLimited += 1;
      return;
    }
    writeLog("room", `error ${code}${rateLimited ? ` (${rateLimited} rate_limited before)` : ""}`);
    rateLimited = 0;
    lastError.value = errorText(code, message);
    if (FINAL_ERRORS.has(code)) {
      // The client stopped for good: nothing may join this room again on its own.
      if ((code === "kicked" || code === "banned") && settings.lastRoom === roomId.value) settings.lastRoom = "";
      roomId.value = "";
    }
  },
};

/** Errors after which the room client stops instead of reconnecting. */
const FINAL_ERRORS = new Set(["room_full", "kicked", "banned", "need_save"]);

function errorText(code: string, message: string): string {
  switch (code) {
    case "room_full":
      return "房间已满(最多 20 人)";
    case "bad_url":
      return "服务器地址无效";
    case "locked":
      return "还没有获得这个物品";
    case "bad_message":
      return "请求无效";
    case "kicked":
    case "banned":
      return "你已被移出这个房间";
    case "need_save":
      return "公开房间需要存档才能加入";
    case "host_needs_save":
      return "需要存档才能公开房间";
    case "host_needs_account":
      return "登录账号后才能公开房间";
    case "not_host":
      return "只有房主可以这样做";
    case "no_member":
      return "这位成员已经离开";
    case "in_duel":
      return "对方正在猜拳";
    case "no_duel":
      return "这个服务器没有猜拳";
    case "duel_locked":
      return "你还不能猜拳";
    case "duel_target_locked":
      return "对方还不能猜拳";
    case "duel_busy":
      return "你正在猜拳";
    case "duel_target_busy":
      return "对方正在猜拳";
    case "duel_cooldown":
      return "稍后再邀请";
    case "duel_cap":
      return "超出今天的上限";
    case "duel_self":
      return "不能和自己猜拳";
    case "no_shards":
      return "碎片不足";
    default:
      return message || code;
  }
}

const client = new RoomClient(events);
let panelMotionIds: string[] = [];
let subscribing = false;
/** Pets mount and leave one by one within a render; the room hears the outcome once. */
function subscribeMotion() {
  if (subscribing) return;
  subscribing = true;
  queueMicrotask(() => {
    subscribing = false;
    client.subscribeMotion([...remoteMotion.ids(), ...panelMotionIds]);
  });
}
if (!isPanelWindow) remoteMotion.onInterest(subscribeMotion);
export function setPanelMotionInterest(ids: string[]): void {
  panelMotionIds = ids;
  subscribeMotion();
}
const motionSender = new MotionSender((pose) => client.sendMotion(pose));
let batcher = new TapBatcher((n) => client.sendTap(n), settings.batchMs);

/** Emote bubble of the local pet (shown immediately, also when offline) and its scratch card or duel win. */
export const localPet = reactive<{ emote: EmoteFrame | null; win: ComboFrame | null; pulse: number }>({
  emote: null, win: null, pulse: 0,
});
const localPlayer = new EmotePlayer((f) => (localPet.emote = f), () => settings.emoteHoldMs);
const localWin = new TapCombo((f) => (localPet.win = f), WIN_MS);
let lastSent = 0;

// ---------------------------------------------------------------- poke
/** The server takes pokes (it lists "poke" in `joined.features`); older servers do not know the message. */
export const pokeOn = ref(false);
/** Who just poked the own pet, for the bubble over it; null once it has closed. */
export const poked = ref<{ id: string; nick: string } | null>(null);
export const POKED_MS = 6000;
/** The server's cooldowns (server/app/rooms.py), kept here too so a poke it would refuse is not sent. */
export const POKE_MS = 3000;
export const POKE_SAME_MS = 10000;
let pokeAt = -Infinity;
const pokedAt = new Map<string, number>();
let pokedTimer: ReturnType<typeof setTimeout> | undefined;

function showPoked(id: string, nick: string): void {
  poked.value = { id, nick };
  clearTimeout(pokedTimer);
  pokedTimer = setTimeout(() => (poked.value = null), POKED_MS);
}
export function closePoked(): void {
  clearTimeout(pokedTimer);
  poked.value = null;
}
function endPokes(): void {
  pokeOn.value = false;
  pokeAt = -Infinity;
  pokedAt.clear();
  closePoked();
}

/** Whether the pet of [m] offers a poke: another member, on a server that takes them, and not click-through. */
export function canPoke(m: Member): boolean {
  return pokeOn.value && !isPanelWindow && !settings.clickThrough && !!youId.value && m.id !== youId.value && members.has(m.id);
}

/** Pokes [id] unless a cooldown says the server would refuse; returns whether it was sent. */
export function poke(id: string, now = Date.now()): boolean {
  const m = members.get(id);
  if (!m || !canPoke(m)) return false;
  if (now - pokeAt < POKE_MS || now - (pokedAt.get(id) ?? -Infinity) < POKE_SAME_MS) return false;
  pokeAt = now;
  pokedAt.set(id, now);
  client.sendPoke(id);
  return true;
}

// ---------------------------------------------------------------- rock-paper-scissors
export const duel = ref<DuelState | null>(null);
let duelTimer: ReturnType<typeof setTimeout> | undefined;

/** The server has duels (its status says so) and this client may take part. */
export const duelOn = computed(() => inRoom.value && !!duelConfig && !!status.value?.duel);
/** An invite or a duel is under way. */
export const duelBusy = computed(() => duel.value?.phase === "invite" || duel.value?.phase === "throw");
/** Invites are turned down: by the setting, and while the pet lets clicks through, as it could not answer them. */
const duelDnd = () => settings.duelDnd || settings.clickThrough;

/** Whether this save looks able to invite [m]: the server checks again, the other save's taps included. */
export function canDuel(m: Member): boolean {
  const mine = me.value;
  const s = status.value;
  return duelOn.value && !!duelConfig && !!s && !!mine && !duelBusy.value && !settings.clickThrough &&
    m.id !== mine.id && !!m.uid && m.uid !== mine.uid && s.totals.taps >= duelConfig.minTaps &&
    duelConfig.stakes.some((x) => stakeOpen(x.bet));
}

/** A bet this save can pay, whose win keeps today's net win within the cap. */
export function stakeOpen(bet: number): boolean {
  const stake = duelConfig?.stakes.find((x) => x.bet === bet);
  const s = status.value;
  return !!stake && !!s?.duel && s.shards >= bet && s.duel.net + stake.prize - stake.bet <= duelConfig!.dailyWinCap;
}

function endDuel(): void {
  clearTimeout(duelTimer);
  duel.value = null;
}

/** Leaves the outcome up for a moment, then clears it (unless another duel took its place). */
function closeDuelLater(): void {
  clearTimeout(duelTimer);
  const shown = duel.value;
  duelTimer = setTimeout(() => { if (duel.value?.id === shown?.id) duel.value = null; }, DUEL_END_MS);
}

const countdown = (sec: number) => ({ sec, until: Date.now() + sec * 1000 });

function onDuelMessage(msg: DuelMessage): void {
  const you = youId.value;
  const d = duel.value;
  switch (msg.type) {
    case "duel_invite": {
      if (msg.from !== you && msg.to !== you) return;
      const otherId = msg.from === you ? msg.to : msg.from;
      const o = members.get(otherId);
      clearTimeout(duelTimer);
      duel.value = {
        id: msg.duel, other: { id: otherId, nick: o ? shownNick(o) : "", character: o?.character ?? "" },
        sent: msg.from === you, bet: msg.bet, prize: msg.prize, phase: "invite", answered: false, round: 0,
        ...countdown(msg.sec), hand: null, shown: null, won: false, reason: "",
      };
      return;
    }
    case "duel_start":
    case "duel_round":
      if (d?.id !== msg.duel) return;
      Object.assign(d, { phase: "throw", round: msg.round, hand: null, ...countdown(msg.sec) });
      if (msg.type === "duel_round") d.shown = { mine: msg.hands[you] ?? null, theirs: msg.hands[d.other.id] ?? null };
      else void reloadStatus(); // the bet is paid
      return;
    case "duel_result":
      // The whole room sees the prize go up over the winner's pet.
      if (msg.winner === you) localWin.add(msg.prize);
      else players.get(msg.winner)?.win.add(msg.prize);
      if (d?.id !== msg.duel) return;
      Object.assign(d, {
        phase: "result", won: msg.winner === you, shown: { mine: msg.hands[you] ?? null, theirs: msg.hands[d.other.id] ?? null },
      });
      closeDuelLater();
      void reloadStatus();
      return;
    case "duel_over":
      if (d?.id !== msg.duel) return;
      Object.assign(d, { phase: "over", reason: msg.reason });
      closeDuelLater();
      void reloadStatus(); // bets go back after idle rounds and draws
      return;
  }
}

/** Panel or desk: invite member [id] at [bet]. */
export function inviteDuel(id: string, bet: number): void {
  if (isPanelWindow) { void requestDesktop("inviteDuel", id, bet); return; }
  const m = members.get(id);
  if (m && canDuel(m) && stakeOpen(bet)) {
    lastError.value = "";
    client.sendDuelInvite(id, bet);
  }
}

/** Desk only: answer the invite on screen. Turning it down closes it at once. */
export function answerDuel(accept: boolean): void {
  const d = duel.value;
  if (!d || d.sent || d.phase !== "invite" || d.answered) return;
  client.sendDuelAnswer(d.id, accept);
  if (accept) d.answered = true;
  else endDuel();
}

/** Desk only: throw a hand in the current round; the first one stands. */
export function throwHand(hand: Hand): void {
  const d = duel.value;
  if (!d || d.phase !== "throw" || d.hand) return;
  d.hand = hand;
  client.sendDuelThrow(d.id, hand);
}

/** Count a tap (key press or click). Only the number is ever sent. */
export function registerTap(): void {
  if (inRoom.value) batcher.add(1);
}

export function syncMotion(pose: PetMotion): void {
  if (!isPanelWindow && inRoom.value) motionSender.update(pose);
}

/** Play an emote on the local pet and send it to the room. Only owned emotes can be sent. */
export function sendEmote(name: string, now = Date.now()): boolean {
  if (isPanelWindow) {
    void requestDesktop("sendEmote", name, now);
    return true;
  }
  if (!ownsEmote(name, collection.owned)) return false;
  if (now - lastSent < SEND_INTERVAL_MS) return false;
  lastSent = now;
  localPlayer.play(name);
  if (inRoom.value) client.sendEmote(name);
  return true;
}

export function setBatchMs(ms: number): void {
  batcher.flush();
  batcher = new TapBatcher((n) => client.sendTap(n), ms);
}

export async function createRoom(): Promise<string> {
  if (isPanelWindow) return requestDesktop("createRoom");
  const base = settings.serverUrl;
  const res = await fetch(`${toHttpBase(base)}/rooms`, { method: "POST" });
  if (!res.ok) throw new Error(`服务器返回 ${res.status}`);
  const data = (await res.json()) as { room: string };
  if (base !== settings.serverUrl) throw new Error("服务器已切换，请重新创建房间");
  return data.room;
}

export function joinRoom(room: string): void {
  if (isPanelWindow) { void requestDesktop("joinRoom", room); return; }
  const id = room.trim();
  if (!id) return;
  lastError.value = "";
  batcher.clear();
  motionSender.clear();
  settings.lastRoom = id;
  roomId.value = id;
  client.join(settings.serverUrl, {
    room: id,
    nick: settings.nick.trim() || "匿名小面包",
    character: settings.character,
    ...(settings.plate ? { plate: settings.plate } : {}),
    ...(activeAccount() ? { accountToken: activeAccount()!.token } : { token }),
    ...(duelDnd() ? { dnd: true } : {}),
  });
}

export function leaveRoom(): void {
  if (isPanelWindow) { void requestDesktop("leaveRoom"); return; }
  batcher.clear();
  motionSender.clear();
  client.leave();
  roomId.value = "";
}

/** Host only: list the room publicly or take it off the list. */
export function setRoomPublic(isPublic: boolean): void {
  if (isPanelWindow) { void requestDesktop("setRoomPublic", isPublic); return; }
  if (isHost.value) client.sendSetPublic(isPublic);
}

/** Host only: remove a member; their save cannot come back until the room closes. */
export function kickMember(id: string): void {
  if (isPanelWindow) { void requestDesktop("kickMember", id); return; }
  if (isHost.value && id !== youId.value && members.has(id)) client.sendKick(id);
}

/** An entry of `GET /rooms` the page can show; anything else from the server is dropped. */
function isPublicRoom(r: unknown): r is PublicRoom {
  const x = r as Partial<PublicRoom> | null;
  return !!x && typeof x === "object" && typeof x.room === "string" && !!x.host && typeof x.host === "object" &&
    typeof x.host.nick === "string" && typeof x.host.character === "string" &&
    typeof x.members === "number" && Number.isFinite(x.members) && typeof x.max === "number" && Number.isFinite(x.max);
}

/**
 * Fetch the public room list. A server without one (404/405) sets it to null, which hides the list;
 * any other failure keeps what was shown (an empty list the first time), so it can be retried.
 * A server with account login lists rooms only for a signed-in account: without one nothing is requested, and the
 * account token goes only to the server it was signed in on. A 401 counts as signed out.
 */
export async function loadPublicRooms(): Promise<void> {
  if (isPanelWindow) return requestDesktop("loadPublicRooms").catch(() => {});
  const base = settings.serverUrl;
  const http = toHttpBase(base);
  const session = activeAccount();
  // A failed request keeps what was shown: the rooms, or the sign-in key while signed out.
  let list: PublicRoom[] | "signin" | null = Array.isArray(publicRooms.value) ? publicRooms.value
    : publicRooms.value === "signin" && !session ? "signin" : [];
  let signedOut = false;
  try {
    if (!session && (await new Api(() => http, () => token).info().catch(() => null))?.accountLogin) list = "signin";
    else {
      const res = await fetch(`${http}/rooms`, session ? { headers: authHeaders({ bearer: session.token }) } : undefined);
      if (res.status === 404 || res.status === 405) list = null;
      else if (res.status === 401) {
        list = "signin";
        const code = ((await res.json().catch(() => null)) as { detail?: { code?: string } } | null)?.detail?.code;
        if (session && code === "account_expired" && account.value?.token === session.token) {
          await setAccount(null);
          signedOut = true;
        }
      } else if (res.ok) {
        const data = (await res.json()) as { rooms?: unknown };
        if (Array.isArray(data.rooms)) list = data.rooms.filter(isPublicRoom);
      }
    }
  } catch {
    /* unreachable for now: keep the list */
  }
  // A sign-in or sign-out during the request reloads the list; this answer is then out of date.
  if (base === settings.serverUrl && (signedOut || activeAccount()?.token === session?.token)) publicRooms.value = list;
}

/** Push profile changes (character / nick / name plate) to the room. */
export function syncProfile(patch: ProfilePatch): void {
  client.sendState({ ...patch, ...(patch.nick !== undefined ? { nick: patch.nick.trim() || "匿名小面包" } : {}) });
}

watch(() => settings.serverUrl, () => {
  if (isPanelWindow) return;
  leaveRoom();
  lastError.value = "";
  publicRooms.value = null;
}, { flush: "sync" });
// Rooms listed for one account are not shown after it signs out; the page asks again.
watch(() => account.value?.token, () => { if (!isPanelWindow) publicRooms.value = null; }, { flush: "sync" });
watch(() => [saveCode.value, account.value?.token], () => {
  if (isPanelWindow) return;
  const previous = roomId.value;
  leaveRoom();
  if (previous) joinRoom(previous);
}, { flush: "sync" });
watch(() => settings.character, (character) => { if (!isPanelWindow) syncProfile({ character }); }, { flush: "sync" });
watch(() => settings.nick, (nick) => { if (!isPanelWindow) syncProfile({ nick }); }, { flush: "sync" });
watch(() => settings.plate, (plate) => { if (!isPanelWindow) syncProfile({ plate }); }, { flush: "sync" });
watch(() => settings.batchMs, (ms) => { if (!isPanelWindow) setBatchMs(ms); });
// Told to the server only when it has duels; the next join carries it either way.
watch(duelDnd, (on) => { if (!isPanelWindow) client.setDnd(on, duelOn.value); }, { flush: "sync" });
