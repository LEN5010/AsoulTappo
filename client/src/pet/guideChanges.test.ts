import { describe, expect, it } from "vitest";
import { touchesGuide } from "./guideChanges";

class Node {
  nodeType = 1;
  children: Node[] = [];
  constructor(private attrs: string[] = []) {}
  add(child: Node) { this.children.push(child); return this; }
  hasAttribute(name: string) { return this.attrs.includes(name); }
  querySelector(sel: string): Node | null {
    for (const c of this.children) if ((sel === "[data-guide]" && c.hasAttribute("data-guide")) || c.querySelector(sel)) return c;
    return null;
  }
}
const text = { nodeType: 3 };
const added = (...nodes: object[]) => ({ type: "childList", addedNodes: nodes, removedNodes: [] }) as unknown as MutationRecord;
const removed = (...nodes: object[]) => ({ type: "childList", addedNodes: [], removedNodes: nodes }) as unknown as MutationRecord;

describe("changes the guide looks again for", () => {
  it("leave out what comes and goes without a guided place in it", () => {
    // An emote bubble, a combo number, a text node.
    expect(touchesGuide([added(new Node(["class"])), removed(new Node().add(new Node())), added(text)])).toBe(false);
    expect(touchesGuide([])).toBe(false);
  });
  it("take a guided place that comes or goes, alone or inside what holds it", () => {
    expect(touchesGuide([added(text), added(new Node(["data-guide"]))])).toBe(true);
    expect(touchesGuide([removed(new Node().add(new Node().add(new Node(["data-guide"]))))])).toBe(true);
  });
  it("take a place that is named or renamed (the observers only watch data-guide)", () => {
    expect(touchesGuide([{ type: "attributes", attributeName: "data-guide" } as unknown as MutationRecord])).toBe(true);
  });
});
