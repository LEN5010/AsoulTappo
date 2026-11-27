import { describe, expect, it } from "vitest";
import { spotlight, spotlightOf } from "./spotlight";

describe("launch spotlight", () => {
  it("is the skins sharing the newest release, titled with their series", () => {
    expect(spotlight).toEqual({ id: "skins:1.3.0", title: "2026生日", skins: ["心宜2026生日"] });
  });

  it("is titled 新皮肤 when the series of the batch differ", () => {
    const skins = [
      { name: "心宜2025生日", since: "1.2.2" },
      { name: "嘉然然龙", since: "1.2.5" },
      { name: "乃琳法师", since: "1.2.5" },
      { name: "贝拉炎头队长", since: "1.2.5" },
    ];
    expect(spotlightOf(skins)).toEqual({ id: "skins:1.2.5", title: "新皮肤", skins: ["嘉然然龙", "乃琳法师", "贝拉炎头队长"] });
  });

  it("follows the newest since and ignores skins without one", () => {
    const skins = [
      { name: "嘉然山海经" },
      { name: "嘉然冬日奇迹", since: "1.2.0" },
      { name: "贝拉春日", since: "1.10.0" },
      { name: "乃琳春日", since: "v1.10.0" },
    ];
    expect(spotlightOf(skins)).toEqual({ id: "skins:1.10.0", title: "春日", skins: ["贝拉春日", "乃琳春日"] });
    expect(spotlightOf([{ name: "嘉然山海经" }])).toBeNull();
  });
});
