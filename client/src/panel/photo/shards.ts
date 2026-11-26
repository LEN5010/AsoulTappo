// Shards thrown from a point into a counter: they leave in a fan, hang for a moment and arc over, as on the draw's board.
const SVG = '<svg viewBox="-2 0 28 24"><path d="M12 3l6 7-6 11-6-11z"/><path class="cut" d="M6 10h12M12 3l-2 7 2 11 2-11z"/></svg>';
const FLIGHT_MS = 640;
const STEP_MS = 45;
const EASE = "cubic-bezier(0.12, 0.6, 0.88, 0.4)";
interface Point { x: number; y: number }

/** [amount] shards fly in [layer] from [from] to [to] (client coordinates); [land] gets each one's share as it arrives. */
export function throwShards(layer: HTMLElement, from: Point, to: Point, amount: number, land: (share: number) => void): void {
  const base = layer.getBoundingClientRect();
  const p0 = { x: from.x - base.left, y: from.y - base.top };
  const p3 = { x: to.x - base.left, y: to.y - base.top };
  const count = amount >= 300 ? 7 : amount >= 40 ? 4 : amount >= 15 ? 3 : 2;
  const each = Math.floor(amount / count);
  for (let k = 0; k < count; k++) {
    const share = k === count - 1 ? amount - each * (count - 1) : each;
    const angle = ((-90 + (k / (count - 1) - 0.5) * 120 + (Math.random() - 0.5) * 18) * Math.PI) / 180;
    const reach = 48 + Math.random() * 26;
    const p1 = { x: p0.x + Math.cos(angle) * reach, y: p0.y + Math.sin(angle) * reach };
    const p2 = { x: p3.x + (p1.x - p3.x) * 0.26, y: Math.max(14, p3.y + 38) };
    const spin = (k % 2 ? 1 : -1) * (220 + Math.random() * 160);
    const frames: Keyframe[] = [];
    for (let i = 0; i <= 24; i++) {
      const t = i / 24, u = 1 - t;
      const at = (a: number, b: number, c: number, d: number) => u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d;
      const scale = t < 0.12 ? 0.3 + (t / 0.12) * 0.9 : t < 0.3 ? 1.2 - ((t - 0.12) / 0.18) * 0.2 : t < 0.86 ? 1 : 1 - ((t - 0.86) / 0.14) * 0.5;
      frames.push({
        transform: `translate(${at(p0.x, p1.x, p2.x, p3.x).toFixed(1)}px, ${at(p0.y, p1.y, p2.y, p3.y).toFixed(1)}px) rotate(${(spin * t).toFixed(1)}deg) scale(${scale.toFixed(3)})`,
        opacity: t < 0.06 ? t / 0.06 : t > 0.95 ? (1 - t) / 0.05 : 1,
      });
    }
    const piece = document.createElement("i");
    piece.className = "shard";
    piece.innerHTML = SVG;
    layer.append(piece);
    const far = Math.hypot(p3.x - p0.x, p3.y - p0.y);
    const flight = piece.animate(frames, { duration: FLIGHT_MS + Math.min(320, far * 0.3), delay: k * STEP_MS, easing: EASE, fill: "both" });
    // A piece taken off the layer on its way (the purse was settled) brings nothing more.
    flight.finished.then(() => { if (piece.isConnected) land(share); }, () => {}).finally(() => piece.remove());
  }
}
