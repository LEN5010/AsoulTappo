// Sounds of the opening, through the app's output (audio/sfx.ts): Kenney's CC0 card recordings, the ones the app
// already uses. The tear is made of grains of the pack-opening recording, one for each bit of the seal that gives, so
// the sound follows the hand.
import { audio, decoded } from "../audio/sfx";

/** What an opening plays. */
export interface PhotoSound {
  /** Decodes the recordings ahead of time. */
  load(): void;
  /** On a press: sound may only start from one. */
  wake(): void;
  tick(q: number, speed: number, pan?: number, strength?: number): void;
  snap(speed: number, pan?: number): void;
  rustle(n: number, ms: number, gain?: number, rate?: number): void;
  slide(gain?: number, rate?: number, pan?: number): void;
  flip(gain?: number, rate?: number, pan?: number): void;
  thud(): void;
  lid(): void;
}

const NAMES = ["pack-open", "slide-1", "slide-2", "slide-3", "flip-1", "flip-2", "flip-3", "flip-4"];
const buffers = new Map<string, AudioBuffer>();
let grains: number[] = [];
let loading = false;

export function load(): void {
  const a = loading ? null : audio();
  if (!a) return;
  loading = true;
  for (const n of NAMES) {
    void decoded(a.ac, n).then((b) => {
      if (!b) return;
      buffers.set(n, b);
      if (n === "pack-open") grains = onsets(b);
    });
  }
}
export function wake(): void {
  audio();
  load();
}

/** Where the recording crackles: the loudest moments, a little apart from each other. */
function onsets(buffer: AudioBuffer): number[] {
  const x = buffer.getChannelData(0), hop = Math.floor(buffer.sampleRate * 0.004);
  const e: number[] = [];
  for (let i = 0; i + hop <= x.length; i += hop) {
    let s = 0;
    for (let k = 0; k < hop; k++) s += x[i + k] * x[i + k];
    e.push(Math.sqrt(s / hop));
  }
  const peaks: [level: number, at: number][] = [];
  for (let i = 2; i < e.length - 8; i++) {
    if (e[i] > e[i - 1] && e[i] >= e[i + 1]) peaks.push([e[i], (i * hop) / buffer.sampleRate]);
  }
  peaks.sort((a, b) => b[0] - a[0]);
  const kept: number[] = [];
  for (const [, at] of peaks) {
    if (kept.every((k) => Math.abs(k - at) > 0.018)) kept.push(at);
    if (kept.length >= 22) break;
  }
  return kept;
}

interface Take {
  at?: number; from?: number; dur?: number;
  gain?: number; rate?: number; pan?: number;
  attack?: number; release?: number;
  hp?: number;
}
function play(name: string, o: Take = {}): void {
  const { at = 0, from = 0, dur = 0, gain = 1, rate = 1, pan = 0, attack = 0.002, release = 0.03, hp = 0 } = o;
  const b = buffers.get(name), a = audio();
  if (!a || a.ac.state !== "running" || !b) return;
  const { ac, out } = a;
  const t = ac.currentTime + at;
  const src = ac.createBufferSource();
  src.buffer = b;
  src.playbackRate.value = rate;
  const g = ac.createGain();
  const len = dur || (b.duration - from) / rate;
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + attack);
  g.gain.setValueAtTime(gain, t + Math.max(attack, len - release));
  g.gain.linearRampToValueAtTime(0, t + len);
  let node: AudioNode = src;
  if (hp) {
    const f = ac.createBiquadFilter();
    f.type = "highpass";
    f.frequency.value = hp;
    node.connect(f);
    node = f;
  }
  const p = ac.createStereoPanner();
  p.pan.value = Math.max(-1, Math.min(1, pan));
  node.connect(g).connect(p).connect(out);
  src.start(t, from, len * rate + 0.02);
}
const rnd = (a: number, b: number) => a + Math.random() * (b - a);
const anyOf = (n: string, k: number) => `${n}-${1 + Math.floor(Math.random() * k)}`;
const grain = () => grains[Math.floor(Math.random() * grains.length)];

/** One bit of the seal gives. [q] is how far along, [speed] 0 to 1. */
export function tick(q: number, speed: number, pan = 0, strength = 1): void {
  if (!grains.length) return;
  const from = grain();
  play("pack-open", {
    from: Math.max(0, from - 0.003), dur: rnd(0.035, 0.06) + 0.03 * speed, gain: (0.42 + 0.5 * speed) * strength,
    rate: 0.94 + 0.34 * q + rnd(-0.07, 0.07), pan, attack: 0.001, release: 0.022,
  });
}
/** The last of it comes away. */
export function snap(speed: number, pan = 0): void {
  play("pack-open", {
    from: 0, dur: 0.30 + 0.14 * (1 - speed), gain: 0.95, rate: 1.16 + 0.22 * speed, pan, attack: 0.001, release: 0.16,
  });
  play("slide-2", { gain: 0.35, rate: 1.5, pan, hp: 900 });
}
/** Foil handled: [n] soft grains over [ms]. */
export function rustle(n: number, ms: number, gain = 0.2, rate = 0.8): void {
  if (!grains.length) return;
  for (let i = 0; i < n; i++) {
    play("pack-open", {
      at: (ms / 1000) * ((i + Math.random()) / n), from: grain(), dur: rnd(0.03, 0.08),
      gain: gain * rnd(0.5, 1), rate: rate * rnd(0.85, 1.2), pan: rnd(-0.5, 0.5), hp: 700,
    });
  }
}
export function slide(gain = 0.5, rate = 1, pan = 0): void {
  play(anyOf("slide", 3), { gain, rate: rate * rnd(0.95, 1.05), pan });
}
export function flip(gain = 0.9, rate = 1, pan = 0): void {
  play(anyOf("flip", 4), { gain, rate: rate * rnd(0.96, 1.04), pan });
}
/** The box set down. */
export function thud(): void {
  play("flip-1", { gain: 0.6, rate: 0.42 });
  play("flip-3", { gain: 0.35, rate: 0.6, at: 0.012 });
}
/** Board sliding on board: the lid. */
export function lid(): void {
  play("slide-1", { gain: 0.8, rate: 0.62 });
  play("flip-2", { gain: 0.5, rate: 0.72, at: 0.26 });
}
