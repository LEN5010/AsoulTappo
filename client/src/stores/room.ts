import { computed, reactive, ref } from "vue";
import { RoomClient, type ConnState, type RoomEvents } from "../net/RoomClient";
import { TapBatcher } from "../net/TapBatcher";
import { toHttpBase, type Member } from "../net/protocol";
import { settings } from "./settings";
import { token } from "./player";
import type { Burst } from "../components/PetView.vue";

export interface RemoteMember extends Member {
  pulse: number;
  bursts: Burst[];
  emote: { key: number; name: string } | null;
}

let seq = 0;

export const conn = ref<ConnState>("idle");
export const roomId = ref("");
export const youId = ref("");
export const lastError = ref("");
export const members = reactive(new Map<string, RemoteMember>());

export const others = computed(() => [...members.values()].filter((m) => m.id !== youId.value));
export const me = computed(() => members.get(youId.value) ?? null);
export const inRoom = computed(() => conn.value === "open" && !!youId.value);

function add(m: Member): void {
  members.set(m.id, { ...m, pulse: 0, bursts: [], emote: null });
}

const events: RoomEvents = {
  onConnState(s) {
    conn.value = s;
    if (s !== "open") {
      // Membership is rebuilt from `joined` after (re)connect.
      members.clear();
      youId.value = "";
    }
  },
  onJoined(room, you, list) {
    roomId.value = room;
    youId.value = you;
    lastError.value = "";
    members.clear();
    list.forEach(add);
  },
  onMemberJoined: add,
  onMemberLeft: (id) => void members.delete(id),
  onTap(id, count, total) {
    const m = members.get(id);
    if (!m) return;
    m.taps = total;
    if (id === youId.value) return; // local pet already reacted instantly
    m.pulse += 1;
    const key = ++seq;
    m.bursts.push({ key, text: `+${count}` });
    if (m.bursts.length > 4) m.bursts.shift();
    setTimeout(() => {
      const i = m.bursts.findIndex((b) => b.key === key);
      if (i >= 0) m.bursts.splice(i, 1);
    }, 800);
  },
  onEmote(id, name) {
    if (id === youId.value) return; // shown locally on send
    const m = members.get(id);
    if (m) showEmote(m, name);
  },
  onState(id, character, nick, frame, badge) {
    const m = members.get(id);
    if (m) {
      m.character = character;
      m.nick = nick;
      m.frame = frame;
      m.badge = badge;
    }
  },
  onError(code, message) {
    lastError.value = errorText(code, message);
  },
};

function errorText(code: string, message: string): string {
  switch (code) {
    case "room_full":
      return "房间已满(最多 20 人)";
    case "bad_url":
      return "服务器地址无效";
    default:
      return message || code;
  }
}

function showEmote(m: { emote: { key: number; name: string } | null }, name: string): void {
  const key = ++seq;
  m.emote = { key, name };
  setTimeout(() => {
    if (m.emote?.key === key) m.emote = null;
  }, 2200);
}

const client = new RoomClient(events);
let batcher = new TapBatcher((n) => client.sendTap(n), settings.batchMs);

/** Local emote bubble for the local pet (shown immediately, also when offline). */
export const localPet = reactive<{ emote: { key: number; name: string } | null }>({ emote: null });

/** Count a tap (key press or click). Only the number is ever sent. */
export function registerTap(): void {
  if (inRoom.value) batcher.add(1);
}

export function sendEmote(name: string): void {
  showEmote(localPet, name);
  if (inRoom.value) client.sendEmote(name);
}

export function setBatchMs(ms: number): void {
  batcher.flush();
  batcher = new TapBatcher((n) => client.sendTap(n), ms);
}

export async function createRoom(): Promise<string> {
  const res = await fetch(`${toHttpBase(settings.serverUrl)}/rooms`, { method: "POST" });
  if (!res.ok) throw new Error(`服务器返回 ${res.status}`);
  const data = (await res.json()) as { room: string };
  return data.room;
}

export function joinRoom(room: string): void {
  const id = room.trim();
  if (!id) return;
  lastError.value = "";
  batcher.clear();
  settings.lastRoom = id;
  roomId.value = id;
  client.join(settings.serverUrl, {
    room: id,
    nick: settings.nick.trim() || "匿名小面包",
    character: settings.character,
    token,
  });
}

export function leaveRoom(): void {
  batcher.clear();
  client.leave();
  roomId.value = "";
}

/** Push profile changes (character / nick / frame / badge) to the room. */
export function syncProfile(patch: { character?: string; nick?: string; frame?: string; badge?: string }): void {
  if (inRoom.value) client.sendState(patch);
}
