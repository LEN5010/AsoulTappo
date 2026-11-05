import type { PetMotion } from "./protocol";

/** Coalesce mouse animation frames; button edges are sent immediately. */
export class MotionSender {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private pending: PetMotion | null = null;
  private last: PetMotion | null = null;

  constructor(private send: (pose: PetMotion) => void, private interval = 50) {}

  update(pose: PetMotion): void {
    this.pending = { ...pose, dx: Math.round(pose.dx * 10) / 10, dy: Math.round(pose.dy * 10) / 10 };
    if (!this.last || pose.keyDown !== this.last.keyDown || pose.left !== this.last.left || pose.right !== this.last.right) {
      this.flush();
    } else if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), this.interval);
    }
  }

  clear(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.pending = this.last = null;
  }

  private flush(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
    const pose = this.pending;
    this.pending = null;
    if (!pose || (this.last && Object.keys(pose).every((key) => pose[key as keyof PetMotion] === this.last![key as keyof PetMotion]))) return;
    this.last = pose;
    this.send(pose);
  }
}
