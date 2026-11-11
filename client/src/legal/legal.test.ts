import { expect, it } from "vitest";
import { DOC_TITLES, DOCS, parseDoc } from ".";

it("reads the title, headings, lists and paragraphs as plain text", () => {
  const doc = parseDoc([
    "# 标题",
    "",
    "第一段",
    "接着第一段",
    "",
    "## 一、小节",
    "",
    "- 第一项",
    "  折行",
    "- 第二项 <b>不是标签</b>",
    "",
    "最后一段",
  ].join("\n"));
  expect(doc.title).toBe("标题");
  expect(doc.blocks).toEqual([
    { kind: "paragraph", text: "第一段接着第一段" },
    { kind: "heading", text: "一、小节" },
    { kind: "list", items: ["第一项折行", "第二项 <b>不是标签</b>"] },
    { kind: "paragraph", text: "最后一段" },
  ]);
});

it("gives both texts a title and sections", () => {
  expect(DOC_TITLES).toEqual({ terms: "用户协议", privacy: "隐私政策" });
  for (const source of Object.values(DOCS)) {
    expect(parseDoc(source).blocks.filter((b) => b.kind === "heading").length).toBeGreaterThan(5);
  }
});
