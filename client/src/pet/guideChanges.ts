// Which page changes concern the guide (pet/DeskGuide.vue, ui/GuideMark.vue): a place marked `data-guide` that
// comes, goes or is renamed. Bubbles and numbers coming and going over the pet do not.

function hasGuide(nodes: NodeList): boolean {
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i] as Element;
    if (node.nodeType !== 1) continue;
    if (node.hasAttribute("data-guide") || node.querySelector("[data-guide]")) return true;
  }
  return false;
}

/** From an observer that watches the subtree's children and only the `data-guide` attribute. */
export function touchesGuide(records: readonly MutationRecord[]): boolean {
  return records.some((r) => r.type === "attributes" || hasGuide(r.addedNodes) || hasGuide(r.removedNodes));
}
