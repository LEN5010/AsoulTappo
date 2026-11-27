import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";
import { expect, it } from "vitest";
import GripMenu from "./GripMenu.vue";

const render = (props: { plate: boolean; shardPop: boolean; docked?: boolean }) =>
  renderToString(createSSRApp({ render: () => h(GripMenu, props) }));

it("folds only a strip that stays: a docked pet's strip has nothing to fold", async () => {
  const pinned = await render({ plate: false, shardPop: true });
  expect(pinned).toContain("收起任务栏");
  expect(pinned).toContain("换成铭牌");
  const docked = await render({ plate: false, shardPop: true, docked: true });
  expect(docked).not.toContain("收起任务栏");
  expect(docked).toContain("换成铭牌");
  expect(docked).toContain("番茄钟");
  expect(docked).toContain("待办");
});

it("offers the strip back under a docked pet that has its plate on the desk", async () => {
  const html = await render({ plate: true, shardPop: false, docked: true });
  expect(html).toContain("换回任务栏");
  expect(html).not.toContain("换成铭牌");
  expect(html).not.toContain("收起任务栏");
});
