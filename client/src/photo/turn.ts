// A card turned by hand: it keeps going a little when let go of, and comes to rest on one of its faces.
import { clamp } from "./math";

export interface Turned {
  yaw: number; pitch: number;
  /** Speeds, degrees a millisecond. */
  vy: number; vp: number;
  /** The face it comes to rest on. */
  to: number;
  held: boolean;
}
export const turned = (): Turned => ({ yaw: 0, pitch: 0, vy: 0, vp: 0, to: 0, held: false });

/** Degrees to a design unit of the hand. */
const YAW = 0.62, PITCH = 0.45;

export function dragTurn(t: Turned, dx: number, dy: number): void {
  t.yaw += dx * YAW;
  t.pitch = clamp(t.pitch - dy * PITCH, -80, 80);
}
/** Let go of at a speed, in design units a millisecond. */
export function dropTurn(t: Turned, vx: number, vy: number): void {
  t.held = false;
  t.vy = vx * YAW;
  t.vp = -vy * PITCH;
  t.to = Math.round((t.yaw + t.vy * 240) / 180) * 180;
}
export function settleTurn(t: Turned, dt: number): void {
  if (t.held) return;
  for (let left = dt; left > 0; left -= 8) {
    const ms = Math.min(8, left);
    t.vy += ((t.to - t.yaw) * 0.00006 - t.vy * 0.0135) * ms;
    t.yaw += t.vy * ms;
    t.vp += (-t.pitch * 0.00006 - t.vp * 0.0135) * ms;
    t.pitch += t.vp * ms;
  }
}
/** It has come to rest. */
export const still = (t: Turned): boolean => (
  !t.held && Math.abs(t.yaw - t.to) < 0.05 && Math.abs(t.pitch) < 0.05 && Math.abs(t.vy) + Math.abs(t.vp) < 0.001);
