// Sounds of the opening: Kenney's CC0 card recordings, the ones the app already uses. The tear is made of grains of the
// pack-opening recording, one for each bit of the seal that gives, so the sound follows the hand.
import { SFX } from "../catalog.js";

const NAMES = ["pack-open", "slide-1", "slide-2", "slide-3", "flip-1", "flip-2", "flip-3", "flip-4"];
let ac = null, out = null;
const buffers = {};
let grains = [];
export const state = { on: true };

export function load() {
  try {
    ac = new AudioContext({ latencyHint: "interactive" });
  } catch { return; }
  const limit = ac.createDynamicsCompressor();
  limit.threshold.value = -12;
  limit.ratio.value = 6;
  out = ac.createGain();
  out.gain.value = 0.9;
  out.connect(limit).connect(ac.destination);
  for (const n of NAMES) {
    fetch(`${SFX}${n}.m4a`).then((r) => r.arrayBuffer()).then((b) => ac.decodeAudioData(b)).then((b) => {
      buffers[n] = b;
      if (n === "pack-open") grains = onsets(b);
    }).catch(() => {});
  }
}
export function wake() { if (ac && ac.state !== "running") void ac.resume(); }

/** Where the recording crackles: the loudest moments, a little apart from each other. */
function onsets(buffer) {
  const x = buffer.getChannelData(0), hop = Math.floor(buffer.sampleRate * 0.004);
  const e = [];
  for (let i = 0; i + hop <= x.length; i += hop) {
    let s = 0;
    for (let k = 0; k < hop; k++) s += x[i + k] * x[i + k];
    e.push(Math.sqrt(s / hop));
  }
  const peaks = [];
  for (let i = 2; i < e.length - 8; i++) if (e[i] > e[i - 1] && e[i] >= e[i + 1]) peaks.push([e[i], (i * hop) / buffer.sampleRate]);
  peaks.sort((a, b) => b[0] - a[0]);
  const kept = [];
  for (const [, at] of peaks) {
    if (kept.every((k) => Math.abs(k - at) > 0.018)) kept.push(at);
    if (kept.length >= 22) break;
  }
  return kept;
}

function play(name, { at = 0, from = 0, dur = 0, gain = 1, rate = 1, pan = 0, attack = 0.002, release = 0.03, hp = 0 } = {}) {
  const b = buffers[name];
  if (!state.on || !ac || ac.state !== "running" || !b) return;
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
  let node = src;
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
const rnd = (a, b) => a + Math.random() * (b - a);
const anyOf = (n, k) => `${n}-${1 + Math.floor(Math.random() * k)}`;

/** One bit of the seal gives. [q] is how far along, [speed] 0 to 1. */
export function tick(q, speed, pan = 0, strength = 1) {
  if (!grains.length) return;
  const from = grains[Math.floor(Math.random() * grains.length)];
  play("pack-open", {
    from: Math.max(0, from - 0.003), dur: rnd(0.035, 0.06) + 0.03 * speed, gain: (0.42 + 0.5 * speed) * strength,
    rate: 0.94 + 0.34 * q + rnd(-0.07, 0.07), pan, attack: 0.001, release: 0.022,
  });
}
/** The last of it comes away. */
export function snap(speed, pan = 0) {
  play("pack-open", { from: 0, dur: 0.30 + 0.14 * (1 - speed), gain: 0.95, rate: 1.16 + 0.22 * speed, pan, attack: 0.001, release: 0.16 });
  play("slide-2", { gain: 0.35, rate: 1.5, pan, hp: 900 });
}
/** Foil handled: [n] soft grains over [ms]. */
export function rustle(n, ms, gain = 0.2, rate = 0.8) {
  if (!grains.length) return;
  for (let i = 0; i < n; i++) {
    play("pack-open", {
      at: (ms / 1000) * ((i + Math.random()) / n), from: grains[Math.floor(Math.random() * grains.length)], dur: rnd(0.03, 0.08),
      gain: gain * rnd(0.5, 1), rate: rate * rnd(0.85, 1.2), pan: rnd(-0.5, 0.5), hp: 700,
    });
  }
}
export function slide(gain = 0.5, rate = 1, pan = 0) { play(anyOf("slide", 3), { gain, rate: rate * rnd(0.95, 1.05), pan }); }
export function flip(gain = 0.9, rate = 1, pan = 0) { play(anyOf("flip", 4), { gain, rate: rate * rnd(0.96, 1.04), pan }); }
/** The box set down. */
export function thud() {
  play("flip-1", { gain: 0.6, rate: 0.42 });
  play("flip-3", { gain: 0.35, rate: 0.6, at: 0.012 });
}
/** Board sliding on board: the lid. */
export function lid() {
  play("slide-1", { gain: 0.8, rate: 0.62 });
  play("flip-2", { gain: 0.5, rate: 0.72, at: 0.26 });
}
