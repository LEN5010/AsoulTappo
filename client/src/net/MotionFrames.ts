import { restingMotion, type PetMotion } from "./protocol";

type Paint = (pose: PetMotion) => void;
type Pose = { target: PetMotion; held: { keyDown: number; left: number; right: number } };
const buttons = ["keyDown", "left", "right"] as const;
/** A press shorter than this is still shown for this long. */
const HOLD_MS = 70;

/**
 * Poses of the other members' pets. Everything heard within a frame is painted once, in that frame: the
 * painter writes the pose to its element and the stylesheet glides the mouse layer there (PetView.vue), so
 * nothing runs between updates. A pose never passes through Vue's reactive graph. The ids with a painter are
 * the ones worth hearing about (onInterest): the room subscribes to exactly those.
 */
export class MotionFrames {
  private poses = new Map<string, Pose>();
  private paints = new Map<string, Set<Paint>>();
  private dirty = new Set<string>();
  private interests = new Set<(ids: string[]) => void>();
  private updates = new Set<(id: string, pose: PetMotion, edge: boolean) => void>();
  private frame: number | null = null;
  private release: ReturnType<typeof setTimeout> | null = null;
  /** Pets shown with a button down that the member has already let go. */
  private holding = new Set<string>();

  constructor(
    private schedule = (cb: FrameRequestCallback) => requestAnimationFrame(cb),
    private cancel = (id: number) => cancelAnimationFrame(id),
    private now = () => performance.now(),
  ) {}

  update(id: string, target: PetMotion): void {
    const pose = this.pose(id);
    const now = this.now();
    const edge = buttons.some((key) => target[key] !== pose.target[key]);
    for (const key of buttons) if (target[key] && !pose.target[key]) pose.held[key] = now + HOLD_MS;
    pose.target = { ...target };
    for (const notify of this.updates) notify(id, pose.target, edge);
    this.touch(id);
  }

  /** A tap heard apart from a key edge (taps travel in batches): the keyboard paw dips once. */
  pulse(id: string): void {
    if (!this.poses.has(id)) return;
    this.pose(id).held.keyDown = this.now() + HOLD_MS;
    this.touch(id);
  }

  /** [paint] is called at once with the pose held, then once per frame in which the pose changed. */
  subscribe(id: string, paint: Paint): () => void {
    let paints = this.paints.get(id);
    if (!paints) { paints = new Set(); this.paints.set(id, paints); }
    paints.add(paint);
    paint(this.shown(this.pose(id), this.now()));
    if (paints.size === 1) this.changed();
    return () => {
      paints!.delete(paint);
      if (paints!.size) return;
      this.paints.delete(id);
      this.dirty.delete(id);
      if (!this.dirty.size && this.frame !== null) { this.cancel(this.frame); this.frame = null; }
      this.changed();
    };
  }

  ids(): string[] { return [...this.paints.keys()]; }
  onInterest(notify: (ids: string[]) => void): () => void {
    this.interests.add(notify);
    notify(this.ids());
    return () => this.interests.delete(notify);
  }
  onUpdate(notify: (id: string, pose: PetMotion, edge: boolean) => void): () => void {
    this.updates.add(notify);
    return () => this.updates.delete(notify);
  }
  remove(id: string): void { this.poses.delete(id); this.dirty.delete(id); }

  private pose(id: string): Pose {
    let pose = this.poses.get(id);
    if (!pose) {
      pose = { target: restingMotion(), held: { keyDown: 0, left: 0, right: 0 } };
      this.poses.set(id, pose);
    }
    return pose;
  }
  private shown(pose: Pose, now: number): PetMotion {
    const out = { ...pose.target };
    for (const key of buttons) out[key] ||= now < pose.held[key];
    return out;
  }
  private changed() { for (const notify of this.interests) notify(this.ids()); }
  private touch(id: string) {
    if (!this.paints.has(id)) return;
    this.dirty.add(id);
    if (this.frame === null) this.frame = this.schedule(this.paint);
  }
  private paint = () => {
    this.frame = null;
    const now = this.now();
    for (const id of this.dirty) {
      const pose = this.poses.get(id);
      if (!pose) continue;
      for (const paint of this.paints.get(id) ?? []) paint(this.shown(pose, now));
      // A button let go while its press is still being shown is painted again when that ends.
      if (buttons.some((key) => !pose.target[key] && pose.held[key] > now)) this.holding.add(id);
      else this.holding.delete(id);
    }
    this.dirty.clear();
    if (this.release !== null || !this.holding.size) return;
    let next = Infinity;
    for (const id of this.holding) {
      const pose = this.poses.get(id);
      for (const key of buttons) if (pose && !pose.target[key] && pose.held[key] > now) next = Math.min(next, pose.held[key]);
    }
    if (next === Infinity) { this.holding.clear(); return; }
    this.release = setTimeout(() => {
      this.release = null;
      for (const id of [...this.holding]) {
        if (this.paints.has(id) && this.poses.has(id)) this.touch(id);
        else this.holding.delete(id);
      }
    }, Math.ceil(next - now));
  };
}

export const remoteMotion = new MotionFrames();
