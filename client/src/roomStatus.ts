// Statuses a member may show in a room, picked from this list only. The server knows the same ids
// (ROOM_STATUSES in server/app/rooms.py) and shows none for any other.

export interface RoomStatus {
  id: string;
  label: string;
  /** An `Icon` name. */
  icon: string;
}

export const ROOM_STATUSES: readonly RoomStatus[] = [
  { id: "fish", label: "摸鱼", icon: "fish" },
  { id: "work", label: "工作", icon: "briefcase" },
  { id: "study", label: "学习", icon: "pencil" },
  { id: "game", label: "打游戏", icon: "gamepad" },
  { id: "music", label: "听歌", icon: "music" },
  { id: "live", label: "看直播", icon: "tv" },
];

/** The status with this id; null for none or one this client does not know. */
export function roomStatus(id: string | null | undefined): RoomStatus | null {
  return ROOM_STATUSES.find((s) => s.id === id) ?? null;
}
