import { computed, reactive, ref, watch } from "vue";
import { RoomClient, type ConnState, type RoomEvents } from "../net/RoomClient";
import { TapBatcher } from "../net/TapBatcher";
import { MotionPlayback } from "../net/MotionPlayback";
import { MotionSender } from "../net/MotionSender";
import { restingMotion, toHttpBase, type Member, type PetMotion, type ProfilePatch } from "../net/protocol";
import { ownsEmote } from "../items";
import { getEmote } from "../manifest";
import { EmotePlayer, SEND_INTERVAL_MS, type EmoteFrame } from "../pet/EmotePlayer";
import { TapCombo, type ComboFrame } from "../pet/TapCombo";
import { settings } from "./settings";
import { activeAccount, account, collection, token, saveCode } from "./player";
import { isPanelWindow } from "../composables/tauri";
import { requestDesktop } from "../desktop/transport";

export interface RemoteMember extends Member {
  /** increments on every tap batch -> short keyboard bounce */
  pulse: number;
  emote: EmoteFrame | null;
  combo: ComboFrame | null;
  motion: PetMotion;
}

export const conn = ref<ConnState>("idle");
export const roomId = ref("");
export const youId = ref("");
export const lastError = ref("");
export const members = reactive(new Map<string, RemoteMember>());
const players = new Map<string, { emote: EmotePlayer; combo: TapCombo; motion: MotionPlayback }>();

export const others = computed(() => [...members.values()].filter((m) => m.id !== youId.value));
export const me = computed(() => members.get(youId.value) ?? null);
export const inRoom = computed(() => conn.value === "open" && !!youId.value);

/** Stable key of a member for remembering where their pet stands on the desk. */
export const memberKey = (m: Member) => m.uid ?? `nick:${m.nick}`;

function add(m: Member): void {
  members.set(m.id, { ...m, pulse: 0, emote: null, combo: null, motion: m.motion ? { ...m.motion } : restingMotion() });
  const rm = members.get(m.id)!;
  players.set(m.id, {
    emote: new EmotePlayer((f) => (rm.emote = f), () => settings.emoteHoldMs),
    combo: new TapCombo((f) => (rm.combo = f)),
    motion: new MotionPlayback(rm.motion),
  });
}

function remove(id: string): void {
  const p = players.get(id);
  p?.emote.clear();
  p?.combo.stop();
  p?.motion.clear();
  players.delete(id);
  members.delete(id);
}

function clearMembers(): void {
  for (const id of [...members.keys()]) remove(id);
}

const events: RoomEvents = {
  onConnState(s) {
    conn.value = s;
    if (s !== "open") {
      motionSender.clear();
      // Membership is rebuilt from `joined` after (re)connect.
      clearMembers();
      youId.value = "";
    }
  },
  onJoined(room, you, list) {
    roomId.value = room;
    youId.value = you;
    lastError.value = "";
    clearMembers();
    list.forEach(add);

  },
  onMemberJoined: add,
  onMemberLeft: remove,
  onTap(id, count, total) {
    const m = members.get(id);
    if (!m) return;
    m.taps = total;
    if (id === youId.value) return; // local pet already reacted instantly
    m.pulse += 1;
    players.get(id)?.combo.add(count);
  },
  onEmote(id, name) {
    if (id === youId.value) return; // shown locally on send
    if (!getEmote(name)) return;
    players.get(id)?.emote.play(name);
  },
  onMotion(id, pose) {
    const member = members.get(id);
    if (member && id !== youId.value) players.get(id)?.motion.update(pose);
  },
  onState(u) {
    const m = members.get(u.id);
    if (!m) return;
    m.character = u.character;
    m.nick = u.nick;
    m.frame = u.frame ?? null;
    m.badge = u.badge ?? null;
  },
  onError(code, message) {
    if (code === "rate_limited") return;
    lastError.value = errorText(code, message);
  },
};

function errorText(code: string, message: string): string {
  switch (code) {
    case "room_full":
      return "房间已满(最多 20 人)";
    case "bad_url":
      return "服务器地址无效";
    case "locked":
      return "还没有获得这个物品";
    default:
      return message || code;
  }
}

const client = new RoomClient(events);
const motionSender = new MotionSender((pose) => client.sendMotion(pose));
let batcher = new TapBatcher((n) => client.sendTap(n), settings.batchMs);

/** Emote bubble of the local pet (shown immediately, also when offline). */
export const localPet = reactive<{ emote: EmoteFrame | null }>({ emote: null });
const localPlayer = new EmotePlayer((f) => (localPet.emote = f), () => settings.emoteHoldMs);
let lastSent = 0;

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
    ...(activeAccount() ? { accountToken: activeAccount()!.token } : { token }),
  });
}

export function leaveRoom(): void {
  if (isPanelWindow) { void requestDesktop("leaveRoom"); return; }
  batcher.clear();
  motionSender.clear();
  client.leave();
  roomId.value = "";
}

/** Push profile changes (character / nick / frame / badge / accessories) to the room. */
export function syncProfile(patch: ProfilePatch): void {
  client.sendState({ ...patch, ...(patch.nick !== undefined ? { nick: patch.nick.trim() || "匿名小面包" } : {}) });
}

watch(() => settings.serverUrl, () => {
  if (isPanelWindow) return;
  leaveRoom();
  lastError.value = "";
}, { flush: "sync" });
watch(() => [saveCode.value, account.value?.token], () => {
  if (isPanelWindow) return;
  const previous = roomId.value;
  leaveRoom();
  if (previous) joinRoom(previous);
}, { flush: "sync" });
watch(() => settings.character, (character) => { if (!isPanelWindow) syncProfile({ character }); }, { flush: "sync" });
watch(() => settings.nick, (nick) => { if (!isPanelWindow) syncProfile({ nick }); }, { flush: "sync" });
watch(() => settings.batchMs, (ms) => { if (!isPanelWindow) setBatchMs(ms); });
