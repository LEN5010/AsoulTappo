// Interface sounds synthesized with Web Audio, so no audio files ship with the client.
// Every sound is a short graph built on demand; settings.sfx turns them all off.
import { settings } from "../stores/settings";
import type { Tell } from "../reveal";

type Wave = OscillatorType;

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let noise: AudioBuffer | null = null;

/** The context starts on the first sound, which always follows a click, so autoplay rules allow it. */
function audio(): { ac: AudioContext; out: GainNode } | null {
  if (!settings.sfx || typeof AudioContext === "undefined") return null;
  if (!ctx) {
    ctx = new AudioContext();
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -10;
    limiter.ratio.value = 8;
    master = ctx.createGain();
    master.gain.value = 0.5;
    master.connect(limiter).connect(ctx.destination);
  }
  if (ctx.state === "suspended") void ctx.resume();
  return { ac: ctx, out: master! };
}

function noiseBuffer(ac: AudioContext): AudioBuffer {
  if (!noise) {
    noise = ac.createBuffer(1, ac.sampleRate, ac.sampleRate);
    const data = noise.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  }
  return noise;
}

/** Gain envelope: quick attack, exponential tail. */
function envelope(ac: AudioContext, at: number, dur: number, peak: number, attack = 0.005): GainNode {
  const g = ac.createGain();
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(peak, at + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  return g;
}

interface ToneOptions { wave?: Wave; gain?: number; to?: number; attack?: number; vibrato?: [rate: number, depth: number] }

function tone(a: { ac: AudioContext; out: AudioNode }, freq: number, at: number, dur: number, o: ToneOptions = {}): void {
  const { ac, out } = a;
  const osc = ac.createOscillator();
  osc.type = o.wave ?? "sine";
  osc.frequency.setValueAtTime(freq, at);
  if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, at + dur);
  if (o.vibrato) {
    const lfo = ac.createOscillator();
    const depth = ac.createGain();
    lfo.frequency.value = o.vibrato[0];
    depth.gain.value = o.vibrato[1];
    lfo.connect(depth).connect(osc.frequency);
    lfo.start(at);
    lfo.stop(at + dur);
  }
  osc.connect(envelope(ac, at, dur, o.gain ?? 0.3, o.attack)).connect(out);
  osc.start(at);
  osc.stop(at + dur + 0.02);
}

interface SweepOptions { from: number; to: number; q?: number; gain?: number; filter?: BiquadFilterType; attack?: number }

function sweep(a: { ac: AudioContext; out: AudioNode }, at: number, dur: number, o: SweepOptions): void {
  const { ac, out } = a;
  const src = ac.createBufferSource();
  src.buffer = noiseBuffer(ac);
  const filter = ac.createBiquadFilter();
  filter.type = o.filter ?? "bandpass";
  filter.Q.value = o.q ?? 1.2;
  filter.frequency.setValueAtTime(o.from, at);
  filter.frequency.exponentialRampToValueAtTime(o.to, at + dur);
  src.connect(filter).connect(envelope(ac, at, dur, o.gain ?? 0.3, o.attack ?? dur * 0.4)).connect(out);
  src.start(at, Math.random() * 0.5);
  src.stop(at + dur + 0.02);
}

const jitter = (value: number, spread = 0.06) => value * (1 + (Math.random() * 2 - 1) * spread);
const note = (semitones: number) => 523.25 * 2 ** (semitones / 12); // from C5

/** Bands sweeping over the page: a paper whoosh landing on a soft thump. */
export function pageTurn(): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  sweep(a, t, 0.34, { from: 500, to: 3200, q: 0.9, gain: 0.22 });
  tone(a, 140, t + 0.26, 0.12, { to: 60, gain: 0.35 });
}

/** One card turning over: a dry snap with a tiny click on top. `soft` for the quick ripple of many cards. */
export function flip(soft = false): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  sweep(a, t, 0.07, { from: jitter(5200), to: jitter(2400), q: 0.7, gain: soft ? 0.14 : 0.24, filter: "highpass", attack: 0.004 });
  tone(a, jitter(1900, 0.08), t, 0.04, { wave: "triangle", gain: soft ? 0.05 : 0.09, attack: 0.002 });
}

const ARPEGGIO = [0, 4, 7, 12, 16, 19, 24];

/** The bands announce the best result: higher rarities climb further and ring longer. */
export function announce(tell: Tell): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  if (tell === "plain") {
    tone(a, note(7), t, 0.35, { gain: 0.16 });
    tone(a, note(12), t + 0.09, 0.45, { gain: 0.14 });
    return;
  }
  const steps = tell === "epic" ? 4 : ARPEGGIO.length;
  const gap = tell === "epic" ? 0.075 : 0.06;
  ARPEGGIO.slice(0, steps).forEach((s, i) => {
    tone(a, note(s), t + i * gap, 0.4, { wave: "triangle", gain: 0.12 });
    tone(a, note(s + 12), t + i * gap, 0.25, { gain: 0.05 });
  });
  if (tell === "epic") return;
  // Hidden cards and skins hold a bright chord with a glittering tail.
  const end = t + steps * gap;
  for (const s of [12, 16, 19, 24]) tone(a, note(s), end, 1.4, { gain: 0.07, attack: 0.03, vibrato: [5, 2] });
  sweep(a, end, 1.1, { from: 6000, to: 11000, q: 6, gain: 0.06, filter: "bandpass", attack: 0.05 });
}

const LIFT_PITCH: Record<string, number> = { legendary: 24, skin: 19, epic: 16, rare: 12 };

/** A card rises into the spotlight: an upward rush and a bell pitched by rarity. */
export function lift(rarity: string): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  sweep(a, t, 0.32, { from: 300, to: 5200, q: 1.1, gain: 0.18 });
  const p = LIFT_PITCH[rarity] ?? 12;
  tone(a, note(p), t + 0.24, 0.9, { gain: 0.14 });
  tone(a, note(p + 7), t + 0.24, 0.6, { gain: 0.06 });
}

/** Poking the alpaca: one of a few silly noises, never the same twice in a row. */
const SILLY = [
  // a nasal, wobbling bleat
  (a: { ac: AudioContext; out: AudioNode }, t: number) => {
    const formant = a.ac.createBiquadFilter();
    formant.type = "bandpass";
    formant.frequency.value = 1100;
    formant.Q.value = 3;
    formant.connect(a.out);
    const voice = { ac: a.ac, out: formant };
    tone(voice, jitter(380), t, 0.55, { wave: "sawtooth", to: jitter(300), gain: 0.9, attack: 0.04, vibrato: [11, 30] });
  },
  // a spring boing
  (a: { ac: AudioContext; out: AudioNode }, t: number) => {
    tone(a, jitter(160), t, 0.5, { to: 520, gain: 0.32, vibrato: [18, 60] });
  },
  // a rubber squeak, twice
  (a: { ac: AudioContext; out: AudioNode }, t: number) => {
    tone(a, jitter(900), t, 0.12, { wave: "square", to: 1500, gain: 0.07 });
    tone(a, jitter(1100), t + 0.15, 0.16, { wave: "square", to: 700, gain: 0.07 });
  },
  // a slide whistle falling over
  (a: { ac: AudioContext; out: AudioNode }, t: number) => {
    tone(a, 1400, t, 0.45, { to: 260, gain: 0.2, vibrato: [7, 25] });
  },
];
let lastSilly = -1;
export function silly(): void {
  const a = audio();
  if (!a) return;
  const first = lastSilly < 0;
  let i = Math.floor(Math.random() * (SILLY.length - (first ? 0 : 1)));
  if (!first && i >= lastSilly) i++;
  lastSilly = i;
  SILLY[i]!(a, a.ac.currentTime);
}
