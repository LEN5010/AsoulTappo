/** Run the mouse layer only while it has visible movement. */
export class MouseMotion {
  private vx = 0;
  private vy = 0;
  private frame: number | null = null;

  constructor(
    private position: { dx: number; dy: number },
    private schedule: (cb: () => void) => number = (cb) => requestAnimationFrame(cb),
    private cancel: (id: number) => void = (id) => cancelAnimationFrame(id),
  ) {}

  move(dx: number, dy: number, sensitivity: number): void {
    if (Math.hypot(dx, dy) > 100 || (dx === 0 && dy === 0)) return;
    this.vx += (dx * sensitivity - this.vx) * 0.3;
    this.vy += (dy * sensitivity - this.vy) * 0.3;
    if (this.frame === null) this.frame = this.schedule(this.tick);
  }

  stop(): void {
    if (this.frame !== null) this.cancel(this.frame);
    this.frame = null;
    this.vx = this.vy = this.position.dx = this.position.dy = 0;
  }

  private tick = (): void => {
    this.frame = null;
    const dx = Math.max(-20, Math.min(20, (this.position.dx + this.vx) * 0.95));
    const dy = Math.max(-20, Math.min(20, (this.position.dy + this.vy) * 0.95));
    this.vx *= 0.7;
    this.vy *= 0.7;
    if (Math.max(Math.abs(dx), Math.abs(dy), Math.abs(this.vx), Math.abs(this.vy)) < 0.01) {
      this.stop();
      return;
    }
    this.position.dx = dx;
    this.position.dy = dy;
    this.frame = this.schedule(this.tick);
  };
}
