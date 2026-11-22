import { describe, expect, it } from "vitest";
import { dropRoom, MAX_RECENT_ROOMS, nameRoom, noteRoom, readRecentRooms, roomDay } from "./recentRooms";

describe("recent rooms", () => {
  it("puts the room just joined in front, once", () => {
    let list = noteRoom([], "a", 1);
    list = noteRoom(list, "b", 2, "茶话会");
    list = noteRoom(list, "a", 3);
    expect(list).toEqual([{ room: "a", at: 3 }, { room: "b", name: "茶话会", at: 2 }]);
  });

  it("keeps the name over a rejoin until the server says otherwise", () => {
    let list = noteRoom([], "b", 1, "茶话会");
    list = noteRoom(list, "b", 5);
    expect(list).toEqual([{ room: "b", name: "茶话会", at: 5 }]);
    expect(nameRoom(list, "b", "夜聊")).toEqual([{ room: "b", name: "夜聊", at: 5 }]);
    expect(nameRoom(list, "b", "")).toEqual([{ room: "b", at: 5 }]);
    expect(nameRoom(list, "x", "夜聊")).toEqual(list);
    // The same name again, or none again, gives back the very list: nothing to save or send.
    const named = nameRoom(list, "b", "夜聊");
    expect(nameRoom(named, "b", "夜聊")).toBe(named);
    const unnamed = [{ room: "c", at: 1 }];
    expect(nameRoom(unnamed, "c", undefined)).toBe(unnamed);
    expect(nameRoom(unnamed, "c", "")).toBe(unnamed);
    expect(nameRoom(list, "x", "夜聊")).toBe(list);
    expect(noteRoom(list, "b", 6, "")).toEqual([{ room: "b", at: 6 }]);
  });

  it("holds the latest few", () => {
    let list = noteRoom([], "r0", 0);
    for (let i = 1; i < MAX_RECENT_ROOMS + 3; i++) list = noteRoom(list, `r${i}`, i);
    expect(list).toHaveLength(MAX_RECENT_ROOMS);
    expect(list[0].room).toBe(`r${MAX_RECENT_ROOMS + 2}`);
    expect(dropRoom(list, list[0].room)).toHaveLength(MAX_RECENT_ROOMS - 1);
  });

  it("reads back only what is well formed", () => {
    expect(readRecentRooms(null)).toEqual([]);
    expect(readRecentRooms([
      { room: "a", at: 5 }, { room: "a", at: 9 }, { room: "", at: 1 }, { room: 3 }, null,
      { room: "b", name: "茶话会", at: 7 }, { room: "c", name: 4, at: "x" },
    ])).toEqual([{ room: "b", name: "茶话会", at: 7 }, { room: "a", at: 5 }, { room: "c", at: 0 }]);
  });

  it("names a day by month and date", () => {
    expect(roomDay(new Date(2026, 10, 7, 12).getTime())).toBe("11-07");
  });
});
