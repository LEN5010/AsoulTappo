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

/** Bands sweeping over the page: a muffled paper rush landing on a soft thump. */
export function pageTurn(): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  sweep(a, t, 0.3, { from: jitter(350), to: jitter(1400), q: 0.8, gain: 0.16 });
  tone(a, 110, t + 0.22, 0.12, { to: 55, gain: 0.22 });
}

/**
 * One card turning over: pure paper, no pitch. The edge lifts, then the card lands a beat later.
 * `soft` for the quick ripple of many cards.
 */
export function flip(soft = false): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  const gain = soft ? 0.1 : 0.17;
  sweep(a, t, 0.06, { from: jitter(1700, 0.12), to: jitter(1100, 0.12), q: 0.9, gain, attack: 0.008 });
  sweep(a, t + 0.05, 0.07, { from: jitter(900, 0.12), to: jitter(500, 0.12), q: 0.9, gain: gain * 0.8, attack: 0.004 });
}

/**
 * The bands announce the best result. Plain batches stay silent; epic gets a low swell of air;
 * hidden cards and skins rise into an impact and the only chord of the whole draw.
 */
export function announce(tell: Tell): void {
  if (tell === "plain") return;
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  if (tell === "epic") {
    sweep(a, t, 0.5, { from: 180, to: 900, q: 0.7, gain: 0.2, filter: "lowpass", attack: 0.32 });
    tone(a, 95, t + 0.3, 0.25, { to: 50, gain: 0.2 });
    return;
  }
  // The riser tracks the tell band sliding in; the hit lands with it.
  const hit = t + 0.26;
  sweep(a, t, 0.28, { from: 400, to: 3600, q: 1, gain: 0.22, attack: 0.26 });
  tone(a, 120, hit, 0.55, { to: 40, gain: 0.45 });
  sweep(a, hit, 0.4, { from: 1800, to: 250, q: 0.6, gain: 0.25, filter: "lowpass", attack: 0.004 });
  for (const s of [-12, -8, -5, 0]) tone(a, note(s), hit, 1.6, { wave: "triangle", gain: 0.055, attack: 0.02, vibrato: [5, 1.5] });
}

/** A card rises into the spotlight on a soft rush; only hidden cards and skins add a bell. */
export function lift(rarity: string): void {
  const a = audio();
  if (!a) return;
  const t = a.ac.currentTime;
  sweep(a, t, 0.3, { from: 250, to: 1800, q: 0.9, gain: 0.12 });
  if (rarity !== "legendary" && rarity !== "skin") return;
  tone(a, note(12), t + 0.24, 1, { gain: 0.09 });
  tone(a, note(19), t + 0.24, 0.6, { gain: 0.035 });
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
