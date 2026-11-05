import { restingMotion, type PetMotion } from "./protocol";

const buttons = ["keyDown", "left", "right"] as const;
/** Keep a short press visible even when down/up arrive within the same render frame. */
export class MotionPlayback {
  private pressed = { keyDown: 0, left: 0, right: 0 };
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  constructor(private target: PetMotion, private holdMs = 70) {}

  update(pose: PetMotion): void {
    this.target.dx = pose.dx;
    this.target.dy = pose.dy;
    const now = performance.now();
    for (const key of buttons) {
      clearTimeout(this.timers.get(key));
      this.timers.delete(key);
      if (pose[key]) {
        if (!this.target[key]) this.pressed[key] = now;
        this.target[key] = true;
      } else {
        const remaining = this.holdMs - (now - this.pressed[key]);
        if (this.target[key] && remaining > 0) {
          this.timers.set(key, setTimeout(() => { this.target[key] = false; this.timers.delete(key); }, remaining));
        } else this.target[key] = false;
      }
    }
  }

  clear(): void {
    this.timers.forEach(clearTimeout);
    this.timers.clear();
    Object.assign(this.target, restingMotion());
  }
}
