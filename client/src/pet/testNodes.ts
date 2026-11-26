// For tests only: elements as plain objects, with what the desk code reads and writes on them (style, class,
// attributes, the tree, boxes), for tests that run without a browser.

export class FakeNode {
  parentElement: FakeNode | null = null;
  children: FakeNode[] = [];
  style: Record<string, string> = {};
  attrs: Record<string, string> = {};
  className = "";
  text = "";
  nodeType: number;
  rect = { left: 0, top: 0, width: 0, height: 0 };
  constructor(public tag: string, kind: "element" | "text" | "comment" = "element") {
    this.nodeType = kind === "element" ? 1 : kind === "text" ? 3 : 8;
  }
  get classList() {
    const tokens = () => this.className.split(/\s+/).filter(Boolean);
    return {
      contains: (c: string) => tokens().includes(c),
      toggle: (c: string, on?: boolean) => {
        const has = tokens().includes(c);
        const want = on ?? !has;
        if (want && !has) this.className = [...tokens(), c].join(" ");
        if (!want && has) this.className = tokens().filter((t) => t !== c).join(" ");
        return want;
      },
    };
  }
  get dataset(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(this.attrs)) {
      if (k.startsWith("data-")) out[k.slice(5).replace(/-([a-z])/g, (_, c: string) => c.toUpperCase())] = v;
    }
    return out;
  }
  get isConnected() { return true; }
  hasAttribute(name: string) { return name in this.attrs; }
  matches(sel: string): boolean {
    if (sel.startsWith(".")) return this.classList.contains(sel.slice(1));
    const attr = /^\[([\w-]+)\]$/.exec(sel);
    if (attr) return this.hasAttribute(attr[1]!);
    return this.tag === sel;
  }
  closest(sel: string): FakeNode | null {
    const any = sel.split(",").map((s) => s.trim());
    for (let n: FakeNode | null = this; n; n = n.parentElement) if (any.some((s) => n!.matches(s))) return n;
    return null;
  }
  querySelectorAll(sel: string): FakeNode[] {
    const out: FakeNode[] = [];
    const walk = (n: FakeNode) => n.children.forEach((c) => { if (c.nodeType === 1 && c.matches(sel)) out.push(c); walk(c); });
    walk(this);
    return out;
  }
  querySelector(sel: string): FakeNode | null { return this.querySelectorAll(sel)[0] ?? null; }
  get childElementCount() { return this.children.filter((c) => c.nodeType === 1).length; }
  getBoundingClientRect() {
    const r = this.rect;
    return { ...r, x: r.left, y: r.top, right: r.left + r.width, bottom: r.top + r.height };
  }
  /** Appends [child] and returns it. */
  append(child: FakeNode): FakeNode {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
}
