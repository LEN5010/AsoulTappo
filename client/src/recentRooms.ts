// The rooms this desk joined lately, kept on this machine (settings.recentRooms) for the online page: newest first,
// each with the name its host gave it when one was known.

export interface RecentRoom {
  room: string;
  /** The room's name as the server last sent it (blocked words masked); missing for none. */
  name?: string;
  /** When this desk last joined it, ms. */
  at: number;
}

export const MAX_RECENT_ROOMS = 6;

/**
 * [list] with [room] joined at [at] in front. [name] undefined keeps the name known so far (a rejoin before the
 * room's info arrives); "" clears it.
 */
export function noteRoom(list: readonly RecentRoom[], room: string, at: number, name?: string): RecentRoom[] {
  const known = list.find((r) => r.room === room);
  const kept = name === undefined ? known?.name : name;
  const entry: RecentRoom = kept ? { room, name: kept, at } : { room, at };
  return [entry, ...list.filter((r) => r.room !== room)].slice(0, MAX_RECENT_ROOMS);
}

/**
 * [list] with [room]'s name as the server now gives it, where it stands. [list] itself when that changes nothing (the
 * room is not listed, or already has that name): room info comes again on every host or listing change, and a new
 * list would save the settings and send them to every window each time.
 */
export function nameRoom(list: RecentRoom[], room: string, name: string | undefined): RecentRoom[] {
  const known = list.find((r) => r.room === room);
  if (!known || (known.name ?? "") === (name ?? "")) return list;
  return list.map((r) => (r.room !== room ? r : name ? { ...r, name } : { room: r.room, at: r.at }));
}

export function dropRoom(list: readonly RecentRoom[], room: string): RecentRoom[] {
  return list.filter((r) => r.room !== room);
}

/** What was stored, as a list this build can show: well-formed entries only, one a room, newest first. */
export function readRecentRooms(raw: unknown): RecentRoom[] {
  if (!Array.isArray(raw)) return [];
  const out: RecentRoom[] = [];
  for (const r of raw) {
    if (!r || typeof r.room !== "string" || !r.room.trim() || r.room.length > 64) continue;
    if (out.some((x) => x.room === r.room)) continue;
    const at = Number.isFinite(r.at) ? Number(r.at) : 0;
    out.push(typeof r.name === "string" && r.name ? { room: r.room, name: r.name.slice(0, 64), at } : { room: r.room, at });
  }
  return out.sort((a, b) => b.at - a.at).slice(0, MAX_RECENT_ROOMS);
}

/** The day [at] (ms) fell on, as "11-17", for a room's line. */
export function roomDay(at: number): string {
  const d = new Date(at);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
