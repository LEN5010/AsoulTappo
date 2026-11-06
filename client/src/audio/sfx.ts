// Interface sounds. The draw uses Kenney's CC0 card recordings, and a skin's spotlight a phrase cut
// from the Quiet backing track (see assets/sfx/LICENSE.md); the alpaca's noises are synthesized. settings.sfx turns them all off.
import { settings } from "../stores/settings";

type Wave = OscillatorType;

let ctx: AudioContext | null = null;
let master: GainNode | null = null;

/** One context for every sound. It starts suspended when created before a click and resumes on the next sound. */
function context(): AudioContext | null {
  if (typeof AudioContext === "undefined") return null;
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
  return ctx;
}

function audio(): { ac: AudioContext; out: GainNode } | null {
  if (!settings.sfx) return null;
  const ac = context();
  return ac ? { ac, out: master! } : null;
}

/** Plays [media] [gain] times louder than its own full volume, which an element cannot do alone. */
export function boost(media: HTMLMediaElement, gain: number): void {
  const ac = context();
  if (!ac) return;
  try {
    const level = ac.createGain();
    level.gain.value = gain;
    ac.createMediaElementSource(media).connect(level).connect(ac.destination);
  } catch { /* already routed, or the browser refuses: it plays at its own volume */ }
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

const jitter = (value: number, spread = 0.06) => value * (1 + (Math.random() * 2 - 1) * spread);

const files = import.meta.glob<string>("../assets/sfx/*.m4a", { eager: true, query: "?url", import: "default" });
const URLS = Object.fromEntries(Object.entries(files).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1, -4), url]));
const buffers = new Map<string, Promise<AudioBuffer | null>>();
/** A sound that decodes later than this after its moment is dropped instead of playing out of step. */
const LATE_S = 0.25;

function decoded(ac: AudioContext, name: string): Promise<AudioBuffer | null> {
  let buffer = buffers.get(name);
  if (!buffer) {
    buffer = fetch(URLS[name]!).then((r) => r.arrayBuffer()).then((b) => ac.decodeAudioData(b)).catch(() => null);
    buffers.set(name, buffer);
  }
  return buffer;
}

/** Decodes every recording ahead of the draw. Decoding works while the context waits for its first click. */
export function prime(): void {
  const a = audio();
  if (a) for (const name of Object.keys(URLS)) void decoded(a.ac, name);
}

function sample(name: string, gain: number, rate = 1): void {
  const a = audio();
  if (!a || !URLS[name]) return;
  const asked = a.ac.currentTime;
  void decoded(a.ac, name).then((buffer) => {
    if (!buffer || a.ac.currentTime - asked > LATE_S) return;
    const src = a.ac.createBufferSource();
    src.buffer = buffer;
    src.playbackRate.value = rate;
    const level = a.ac.createGain();
    level.gain.value = gain;
    src.connect(level).connect(a.out);
    src.start();
  });
}

const anyOf = (prefix: string, count: number) => `${prefix}-${1 + Math.floor(Math.random() * count)}`;

/** Bands sweep over the page as a pack tears open. */
export function pageTurn(): void {
  sample("pack-open", 1.12);
}

/** A card turned face up and set down; one of four takes, slightly retuned. `soft` for the quick ripple. */
export function flip(soft = false): void {
  sample(anyOf("flip", 4), soft ? 0.56 : 0.98, jitter(1, 0.04));
}

let theme: { ac: AudioContext; src: AudioBufferSourceNode; level: GainNode } | null = null;
let themeRound = 0;

/** A skin brings no sound of its own to the spotlight, so it gets the closing phrase of Quiet. */
export function startTheme(): void {
  stopTheme(0.1);
  const a = audio();
  if (!a) return;
  const mine = ++themeRound;
  const asked = a.ac.currentTime;
  void decoded(a.ac, "skin-theme").then((buffer) => {
    if (!buffer || mine !== themeRound || a.ac.currentTime - asked > LATE_S) return;
    const src = a.ac.createBufferSource();
    src.buffer = buffer;
    const level = a.ac.createGain();
    level.gain.value = 1;
    src.connect(level).connect(a.out);
    src.onended = () => { if (theme?.src === src) theme = null; };
    src.start();
    theme = { ac: a.ac, src, level };
  });
}

export function stopTheme(fade = 0.5): void {
  themeRound++;
  if (!theme) return;
  const { ac, src, level } = theme;
  theme = null;
  const t = ac.currentTime;
  level.gain.cancelScheduledValues(t);
  level.gain.setValueAtTime(level.gain.value, t);
  level.gain.linearRampToValueAtTime(0.0001, t + fade);
  src.stop(t + fade + 0.05);
}

/** A card slides off its tile into the spotlight. */
export function lift(): void {
  sample(anyOf("slide", 3), 0.84);
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
