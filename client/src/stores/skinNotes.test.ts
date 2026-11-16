import { beforeEach, describe, expect, it } from "vitest";
import { loadSettings, settings } from "./settings";
import { setSkinNote, shownSkinName, skinNote } from "./skinNotes";

const store = (v: unknown) => ({ getItem: () => JSON.stringify(v) });

describe("skin notes", () => {
  beforeEach(() => { settings.skinNotes = {}; });

  it("replace the skin's title until cleared", () => {
    expect(shownSkinName("嘉然山海经")).toBe("嘉然帝江");
    setSkinNote("嘉然山海经", "  小帝江  ");
    expect(skinNote("嘉然山海经")).toBe("小帝江");
    expect(shownSkinName("嘉然山海经")).toBe("小帝江");
    setSkinNote("嘉然山海经", " ");
    expect(shownSkinName("嘉然山海经")).toBe("嘉然帝江");
    expect(settings.skinNotes).toEqual({});
  });

  it("keep ten characters and drop a note equal to the title", () => {
    setSkinNote("贝拉山海经", "一二三四五六七八九十十一");
    expect(skinNote("贝拉山海经")).toBe("一二三四五六七八九十");
    setSkinNote("贝拉山海经", "贝拉毕方");
    expect(skinNote("贝拉山海经")).toBe("");
  });

  it("leave the other skins' notes alone", () => {
    setSkinNote("嘉然山海经", "甲");
    setSkinNote("乃琳山海经", "乙");
    setSkinNote("嘉然山海经", "");
    expect(settings.skinNotes).toEqual({ 乃琳山海经: "乙" });
  });

  it("load only string notes, trimmed and cut", () => {
    const s = loadSettings(store({ skinNotes: { 嘉然山海经: " 甲 ", 乃琳山海经: 3, 贝拉山海经: "", 心宜2025生日: "一二三四五六七八九十十一" } }));
    expect(s.skinNotes).toEqual({ 嘉然山海经: "甲", 心宜2025生日: "一二三四五六七八九十" });
    expect(loadSettings(store({ skinNotes: ["x"] })).skinNotes).toEqual({});
  });
});
