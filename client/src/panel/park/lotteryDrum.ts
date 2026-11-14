// The daily lottery's draw machine as a small 2D simulation: numbered balls in a round glass globe, under gravity,
// bouncing off the glass and each other with some loss, spinning as they roll, and, while the air is on, blown up by
// a jet from the bottom centre that weakens with height and wavers over time, so they rise up the middle, tumble in
// the upper half and fall back down the sides. A ball can be pulled to the outlet, where it leaves the globe.
// Units are px and seconds. The globe's centre is the origin, y points down, angles run clockwise (as CSS rotate).

export interface DrumBall {
  d: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Turned so far (radians) and turning speed (radians per second). */
  a: number;
  w: number;
  /** This ball's own phase in the air's wavering. */
  ph: number;
}

/** Gravity, px/s². */
const GRAVITY = 1500;
/** The simulation advances in steps of this many seconds. */
export const STEP = 1 / 120;
/** Bounce kept off the glass and off another ball; slower impacts than BOUNCE_MIN do not bounce at all. */
const WALL_BOUNCE = 0.5;
const BALL_BOUNCE = 0.8;
const BOUNCE_MIN = 40;
/** How much of the slip at a contact friction takes away (1: the ball rolls at once). */
const GRIP = 0.55;
/** Air drag on moving and on turning, per second. */
const DRAG = 0.4;
const SPIN_DRAG = 0.8;
/** The air comes on and dies away over this long. */
const AIR_RAMP = 0.4;
/** A pulled ball is drawn to the outlet this hard (in g) and leaves once this close (px), or after PULL_MAX s. */
const PULL = 7;
const PULL_NEAR = 3;
const PULL_MAX = 0.9;
/** Still means slower than this (px/s, rad/s) for QUIET s. */
const STILL_V = 18;
const STILL_W = 2;
const QUIET = 0.3;
/** Contact passes per step. */
const SOLVE = 4;

/** A small seeded random source (mulberry32), so a drum always falls into the same pile. */
function random(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Pull { since: number; out: (b: DrumBall) => void }

export class Drum {
  balls: DrumBall[] = [];
  /** The air now and where it is heading, 0 to 1. */
  air = 0;
  airTarget = 0;
  t = 0;
  /** Where a pulled ball heads: the glass's outlet, as a ball centre just inside the rim. */
  outlet: { x: number; y: number };
  private pulls = new Map<string, Pull>();
  private quiet = 0;
  private left = 0;
  private rand: () => number;

  /** A globe of inner radius [R] with balls of radius [r]; the outlet is on the rim at [outletAngle] (radians). */
  constructor(readonly R: number, readonly r: number, outletAngle: number, seed = 7) {
    this.rand = random(seed);
    this.outlet = { x: (R - r) * Math.cos(outletAngle), y: (R - r) * Math.sin(outletAngle) };
  }

  has(d: string): boolean {
    return this.balls.some((b) => b.d === d);
  }

  /** Adds ball [d] in the upper part of the globe, moving a little, to fall in with the rest. */
  add(d: string): DrumBall {
    const span = this.R - this.r;
    const b: DrumBall = {
      d,
      x: (this.rand() - 0.5) * span,
      y: -span * (0.2 + this.rand() * 0.5),
      vx: (this.rand() - 0.5) * 120,
      vy: (this.rand() - 0.5) * 60,
      a: (this.rand() - 0.5) * 1.2,
      w: 0,
      ph: this.rand() * Math.PI * 2,
    };
    this.balls.push(b);
    this.quiet = 0;
    return b;
  }

  remove(d: string): void {
    const i = this.balls.findIndex((b) => b.d === d);
    if (i >= 0) this.balls.splice(i, 1);
    this.pulls.delete(d);
  }

  /** Draws ball [d] to the outlet; [out] gets it as it leaves the globe. False when there is no such ball. */
  pull(d: string, out: (b: DrumBall) => void): boolean {
    if (!this.has(d)) return false;
    this.pulls.set(d, { since: this.t, out });
    this.quiet = 0;
    return true;
  }

  get pulling(): boolean {
    return this.pulls.size > 0;
  }

  /**
   * Hands this drum over to [next], the globe at a new size: the same balls (falling in afresh there), the air, and
   * every pull still waiting, each with its own handler. This drum is left empty.
   */
  handOver(next: Drum): void {
    for (const b of this.balls) if (!next.has(b.d)) next.add(b.d);
    for (const b of [...next.balls]) if (!this.has(b.d)) next.remove(b.d);
    next.air = this.air;
    next.airTarget = this.airTarget;
    for (const [d, p] of this.pulls) next.pull(d, p.out);
    this.pulls.clear();
    this.balls = [];
  }

  /** Lets every ball still being pulled leave now, wherever it is: the globe is going away. */
  release(): void {
    const pulls = [...this.pulls];
    this.pulls.clear();
    for (const [d, p] of pulls) {
      const b = this.balls.find((x) => x.d === d);
      if (!b) continue;
      this.remove(d);
      p.out(b);
    }
  }

  /** Nothing moves and nothing will until the air or a pull starts. */
  get settled(): boolean {
    return this.air === 0 && this.airTarget === 0 && !this.pulls.size && this.quiet >= QUIET;
  }

  /** Advances [dt] seconds in fixed steps (the rest carries over to the next call). */
  update(dt: number): void {
    this.left = Math.min(this.left + dt, 0.1);
    while (this.left >= STEP) {
      this.step(STEP);
      this.left -= STEP;
    }
  }

  /** Runs with the air off until everything rests (or [most] seconds), as when the globe is first filled. */
  settle(most = 6): void {
    this.air = 0;
    this.airTarget = 0;
    this.pulls.clear();
    for (let s = 0; s < most && !this.settled; s += STEP) this.step(STEP);
    for (const b of this.balls) b.vx = b.vy = b.w = 0;
    this.quiet = QUIET;
  }

  private step(h: number): void {
    this.t += h;
    const { R } = this;
    // The air eases towards its target over AIR_RAMP.
    const ramp = h / AIR_RAMP;
    this.air = this.air < this.airTarget ? Math.min(this.airTarget, this.air + ramp) : Math.max(this.airTarget, this.air - ramp);
    const t = this.t;
    const jet = this.air * GRAVITY * (1 + 0.3 * Math.sin(2.1 * t) + 0.2 * Math.sin(5.3 * t + 1.3));

    for (const b of this.balls) {
      let fx = 0;
      let fy = GRAVITY;
      const pull = this.pulls.get(b.d);
      if (pull) {
        const dx = this.outlet.x - b.x;
        const dy = this.outlet.y - b.y;
        const len = Math.hypot(dx, dy) || 1;
        fx += (dx / len) * PULL * GRAVITY;
        fy += (dy / len) * PULL * GRAVITY - GRAVITY;
        const damp = Math.exp(-4 * h);
        b.vx *= damp;
        b.vy *= damp;
      } else if (jet) {
        // depth: 0 at the top of the globe, 1 at the bottom. The jet is strongest low and in the middle.
        const depth = (b.y + R) / (2 * R);
        const core = Math.exp(-((b.x / (0.5 * R)) ** 2));
        fy -= jet * (1 + 3.2 * depth ** 1.5) * core;
        // Low down the air draws balls in towards the jet; everywhere it wavers, each ball in its own phase.
        fx -= (b.x / R) * this.air * GRAVITY * 1.4 * depth * depth;
        fx += this.air * GRAVITY * 1.3 * (Math.sin(3.3 * t + b.ph) + 0.6 * Math.sin(7.9 * t + 2 * b.ph));
        fy += this.air * GRAVITY * 1.0 * (Math.sin(4.1 * t + 1.7 * b.ph) + 0.5 * Math.sin(9.7 * t + b.ph));
      }
      b.vx += fx * h;
      b.vy += fy * h;
      const drag = Math.exp(-DRAG * h);
      b.vx *= drag;
      b.vy *= drag;
      b.w *= Math.exp(-SPIN_DRAG * h);
      b.x += b.vx * h;
      b.y += b.vy * h;
      b.a += b.w * h;
    }

    // Contacts, a few passes so a pile holds: ball against ball (push apart, bounce along the normal) and ball against
    // the glass; friction along the tangent, on the first pass, turns them.
    for (let pass = 0; pass < SOLVE; pass++) {
      this.collide(pass === 0);
      this.glass(pass === 0);
    }

    // A pulled ball at the outlet leaves the globe.
    for (const [d, pull] of this.pulls) {
      const b = this.balls.find((x) => x.d === d);
      if (!b) {
        this.pulls.delete(d);
        continue;
      }
      if (Math.hypot(b.x - this.outlet.x, b.y - this.outlet.y) <= PULL_NEAR || t - pull.since >= PULL_MAX) {
        this.remove(d);
        pull.out(b);
      }
    }

    const still = this.balls.every((b) => Math.hypot(b.vx, b.vy) < STILL_V && Math.abs(b.w) < STILL_W);
    this.quiet = still && this.air === 0 && !this.pulls.size ? this.quiet + h : 0;
    // At rest the pile sleeps: no creeping from the contact solver.
    if (this.quiet >= QUIET) for (const b of this.balls) b.vx = b.vy = b.w = 0;
  }

  private collide(friction: boolean): void {
    const { balls, r } = this;
    const n = balls.length;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const p = balls[i]!;
        const q = balls[j]!;
        let dx = q.x - p.x;
        let dy = q.y - p.y;
        const dist = Math.hypot(dx, dy);
        if (dist >= 2 * r || dist === 0) continue;
        dx /= dist;
        dy /= dist;
        const push = (2 * r - dist) / 2;
        p.x -= dx * push;
        p.y -= dy * push;
        q.x += dx * push;
        q.y += dy * push;
        const vn = (q.vx - p.vx) * dx + (q.vy - p.vy) * dy;
        if (vn < 0) {
          const e = -vn > BOUNCE_MIN ? BALL_BOUNCE : 0;
          const jn = (-(1 + e) * vn) / 2;
          p.vx -= jn * dx;
          p.vy -= jn * dy;
          q.vx += jn * dx;
          q.vy += jn * dy;
        }
        if (!friction) continue;
        // Tangent (-ny, nx); the slip of p's contact point against q's.
        const tx = -dy;
        const ty = dx;
        const slip = (p.vx - q.vx) * tx + (p.vy - q.vy) * ty + (p.w + q.w) * r;
        const jt = (GRIP * slip) / 6;
        p.vx -= jt * tx;
        p.vy -= jt * ty;
        q.vx += jt * tx;
        q.vy += jt * ty;
        p.w -= (2 * jt) / r;
        q.w -= (2 * jt) / r;
      }
    }
  }

  private glass(friction: boolean): void {
    const { r } = this;
    const lim = this.R - r;
    for (const b of this.balls) {
      const dist = Math.hypot(b.x, b.y);
      if (dist <= lim) continue;
      const nx = b.x / dist;
      const ny = b.y / dist;
      b.x = nx * lim;
      b.y = ny * lim;
      const vn = b.vx * nx + b.vy * ny;
      if (vn > 0) {
        const e = vn > BOUNCE_MIN ? WALL_BOUNCE : 0;
        b.vx -= (1 + e) * vn * nx;
        b.vy -= (1 + e) * vn * ny;
      }
      if (!friction) continue;
      const tx = -ny;
      const ty = nx;
      const slip = b.vx * tx + b.vy * ty + b.w * r;
      const jt = (GRIP * slip) / 3;
      b.vx -= jt * tx;
      b.vy -= jt * ty;
      b.w -= (2 * jt) / r;
    }
  }
}
