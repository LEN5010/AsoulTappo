// The hall (公开桌): the public open tables the lobby lists at each stake (GET /api/ddz/lobby, `tiers[].tables`), which a
// save sits down at from its dou dizhu connection with no accept step. A server without the hall lists none, and the
// sheet then waits in the queue as before.
import type { DdzHallTable, DdzLobby } from "../net/protocol";

/** How many tables of a stake the sheet lists. */
export const HALL_ROWS = 3;

/** The server has the hall: its lobby lists `tables` on its stakes. */
export const hallOn = (lobby: DdzLobby | null | undefined): boolean => !!lobby?.tiers.some((t) => Array.isArray(t.tables));

const tablesAt = (lobby: DdzLobby | null | undefined, base: number): DdzHallTable[] =>
  lobby?.tiers.find((t) => t.base === base)?.tables ?? [];

/** [got], a lobby just read, with the tables of [held] where the server said its list is still the one held
 *  (`hallSame`); the rest of [got] is new. */
export function withHeldTables(got: DdzLobby, held: DdzLobby | null | undefined): DdzLobby {
  if (!got.hallSame || !held) return got;
  return { ...got, tiers: got.tiers.map((t) => ({ ...t, tables: tablesAt(held, t.base) })) };
}

/** The tables listed at [base] that the save may sit down at, the own one [own] left out, at most [max]. */
export function hallTables(lobby: DdzLobby | null | undefined, base: number, own?: string, max = HALL_ROWS): DdzHallTable[] {
  return tablesAt(lobby, base).filter((t) => t.table !== own && t.seats.some((s) => !s)).slice(0, max);
}

/** Saves sitting at the tables listed at [base] (seats offered to the queue not counted), the save itself at [own] left out. */
export function hallSeated(lobby: DdzLobby | null | undefined, base: number, own?: string): number {
  return tablesAt(lobby, base).reduce((n, t) => {
    const taken = t.seats.filter((s) => !!s && !("pending" in s)).length;
    return n + (t.table === own ? Math.max(0, taken - 1) : taken);
  }, 0);
}

export type HallFace = { character: string; nick: string };
/**
 * The seats where a sit goes: those of [table] with [me] in its first empty seat (taken ones by [shown], offered ones
 * "pending"), or [me] in the middle of an empty table.
 */
export function hallPreview(
  table: DdzHallTable | undefined, me: HallFace, shown: (s: HallFace) => HallFace = (s) => s,
): (HallFace | null | "pending")[] {
  if (!table) return [null, me, null];
  let mine = false;
  return table.seats.map((s) => {
    if (s && "pending" in s) return "pending";
    if (s) return shown(s);
    if (mine) return null;
    mine = true;
    return me;
  });
}
