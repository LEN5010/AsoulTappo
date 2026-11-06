<script setup lang="ts">
// The page-turn bands, played for a draw: they cover the scene while the request runs, a third band
// announces the best result in its tone, then all of them carry on off to the right.
import { computed, ref } from "vue";
import { EASE_IN_OUT, EASE_OUT } from "../ui/motion";
import type { Tell } from "../reveal";
import Icon from "../ui/Icon.vue";

const props = defineProps<{
  count: number;
  tell: Tell;
  /** What the announcement says under its word, e.g. 大隐藏 · 皮肤, or 史诗 ×2 for an epic batch. */
  tellLabel: string;
  tellStyle?: Record<string, string>;
}>();

const LEFT = "translateX(-112%)";
const HOME = "translateX(0)";
const RIGHT = "translateX(112%)";
const COVER_MS = 200;
const TELL_MS = 260;
const TELL_HOLD_MS = 700;
const EPIC_HOLD_MS = 380;
const STREAK_MS = 520;
const LEAVE_MS = 320;
const LAG_MS = 40;

const WORD: Record<Tell, string> = { plain: "", epic: "", skin: "SKIN", legendary: "SECRET" };
const word = computed(() => WORD[props.tell]);
const TITLE = [..."RESONANCE"];
const BURST = Array.from({ length: 12 }, (_, n) => ({
  angle: `${n * 30 + (n % 2) * 9}deg`,
  reach: `${150 + (n % 4) * 46}px`,
  size: n % 3 === 0 ? 30 : n % 3 === 1 ? 16 : 22,
  delay: `${(n % 4) * 30}ms`,
}));

const root = ref<HTMLElement>();
const under = ref<HTMLElement>();
const over = ref<HTMLElement>();
const tellBand = ref<HTMLElement>();
const streak = ref<HTMLElement>();
const tellStreak = ref<HTMLElement>();
/** Bumped on every cover so the title's letters rise again. */
const take = ref(0);
const sparking = ref(false);

/** A band of light crossing, the same one that crosses a primary button under the pointer. */
const shine = (el: HTMLElement) => el.animate(
  [{ transform: "translateX(-100%)", opacity: 0 }, { opacity: 1, offset: 0.2 }, { transform: "translateX(100%)", opacity: 0 }],
  { duration: STREAK_MS, easing: EASE_OUT },
);
const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const done = (list: Animation[]) => Promise.allSettled(list.map((a) => a.finished)).then(() => undefined);
function slide(els: HTMLElement[], from: string, to: string, duration: number): Animation[] {
  return els.map((el, i) =>
    el.animate([{ transform: from }, { transform: to }], { duration, delay: i * LAG_MS, easing: EASE_IN_OUT, fill: "both" }),
  );
}

let held: Animation[] = [];
function hold(list: Animation[]) {
  held.forEach((a) => a.cancel());
  held = list;
  return done(list);
}

/** Bands in, title up. Resolves once the scene is covered. */
function cover(): Promise<void> {
  take.value += 1;
  sparking.value = false;
  root.value!.style.visibility = "visible";
  return hold(slide([under.value!, over.value!], LEFT, HOME, COVER_MS));
}

/** Plays the announcement for the batch that just landed. A plain batch has none. */
async function announce(): Promise<void> {
  if (props.tell === "plain") return;
  if (props.tell === "epic") {
    sparking.value = true;
    shine(streak.value!);
    await wait(EPIC_HOLD_MS);
    return;
  }
  const anim = tellBand.value!.animate([{ transform: LEFT }, { transform: HOME }], { duration: TELL_MS, easing: EASE_IN_OUT, fill: "both" });
  held.push(anim);
  await done([anim]);
  sparking.value = true;
  shine(tellStreak.value!);
  await wait(TELL_HOLD_MS);
}

/** Every band leaves to the right, uncovering the board. */
async function leave(): Promise<void> {
  const covered = [tellBand.value, over.value!, under.value!].filter((el): el is HTMLElement => !!el);
  await hold(slide(covered, HOME, RIGHT, LEAVE_MS));
  root.value!.style.visibility = "hidden";
  sparking.value = false;
}

defineExpose({ cover, announce, leave });
</script>

<template>
  <div ref="root" class="bands" aria-hidden="true">
    <div ref="under" class="band under"></div>
    <div ref="over" class="band over">
      <i v-if="sparking && tell === 'epic'" class="deepen"></i>
      <span :key="take" class="title">
        <b class="letters"><i v-for="(c, n) in TITLE" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <small>共鸣 ×{{ count }}</small>
        <template v-if="sparking && tell === 'epic'">
          <span class="chip ui-tag dark">{{ tellLabel }}</span>
          <Icon v-for="n in 2" :key="n" name="spark" :size="n === 1 ? 26 : 16" class="spark" :class="`s${n + 2}`" />
        </template>
      </span>
      <i ref="streak" class="streak"></i>
    </div>
    <div v-if="word" ref="tellBand" class="band tell" :class="`tone-${tell}`" :style="tellStyle">
      <template v-if="sparking">
        <i class="flash"></i>
        <span class="burst">
          <i v-for="(s, n) in BURST" :key="n" :style="{ '--a': s.angle, '--d': s.reach, '--delay': s.delay }">
            <Icon name="spark" :size="s.size" />
          </i>
        </span>
      </template>
      <span v-if="sparking" class="title">
        <b class="letters stamp"><i v-for="(c, n) in [...word]" :key="n" :style="{ '--n': n }">{{ c }}</i></b>
        <small class="label">{{ tellLabel }}</small>
        <Icon v-for="n in 5" :key="n" name="spark" :size="n % 2 ? 30 : 18" class="spark" :class="`s${n}`" />
      </span>
      <i ref="tellStreak" class="streak"></i>
    </div>
  </div>
</template>

<style scoped>
.bands {
  position: absolute;
  inset: 0;
  z-index: 8;
  overflow: hidden;
  pointer-events: none;
  visibility: hidden;
}
.band {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: -8%;
  width: 116%;
  overflow: hidden;
  transform: translateX(-112%);
  will-change: transform;
}
.under {
  background: var(--c-200);
}
.over {
  background: var(--c-500);
}
/* An epic batch sinks the band to the epic back's wine. */
.deepen {
  position: absolute;
  inset: 0;
  background: var(--c-800);
  animation: deepen-in 320ms var(--ease-out) both;
}
.tell {
  background: var(--tone-fill);
  color: var(--tone-ink);
}
.title {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  white-space: nowrap;
}
.letters {
  display: flex;
  font: 800 clamp(64px, 17cqw, 112px)/0.9 var(--font-latin);
  letter-spacing: 0.01em;
  color: #fff;
  text-shadow: 0 2px 0 rgba(var(--c-900-rgb), 0.08);
}
.letters i {
  display: block;
  font-style: normal;
  animation: letter-rise 420ms var(--ease-spring) calc(60ms + var(--n) * 24ms) both;
}
/* The announcement word comes down like a stamp, letter by letter. */
.stamp i {
  animation: letter-stamp 420ms var(--ease-out) calc(var(--n) * 45ms) both;
}
.title small {
  margin-top: 6px;
  font: 800 var(--fs-title) var(--font);
  color: var(--ink);
  animation: label-in 320ms var(--ease-out) 120ms both;
}
.tell .title small {
  color: var(--tone-ink);
}
.tell .label {
  animation-delay: 300ms;
}
.chip {
  position: absolute;
  right: 2px;
  bottom: 6px;
  font-size: var(--fs-label);
  line-height: 22px;
  padding: 0 10px;
  animation: chip-stamp 380ms var(--ease-pop) both;
}
.streak {
  position: absolute;
  inset: 0;
  z-index: 3;
  background: linear-gradient(105deg, transparent 36%, rgba(255, 255, 255, 0.62) 50%, transparent 64%);
  opacity: 0;
  transform: translateX(-100%);
}
.flash {
  position: absolute;
  inset: 0;
  z-index: 4;
  background: #fff;
  animation: band-flash 520ms var(--ease-out) both;
}
.burst {
  position: absolute;
  z-index: 1;
  left: 50%;
  top: 50%;
}
.burst i {
  position: absolute;
  left: 0;
  top: 0;
  rotate: var(--a);
  transform-origin: 0 0;
}
.burst svg {
  position: absolute;
  left: 0;
  top: 0;
  stroke-width: 0;
  fill: #fff;
  filter: drop-shadow(0 1px 2px rgba(var(--c-900-rgb), 0.2));
  animation: burst-fly 820ms var(--ease-out) calc(120ms + var(--delay)) both;
}
.spark {
  position: absolute;
  stroke-width: 0;
  fill: #fff;
  filter: drop-shadow(0 1px 2px rgba(var(--c-900-rgb), 0.2));
  animation: spark-pop 620ms var(--ease-pop) 260ms both;
}
.s1 { left: -14%; top: -18%; animation-delay: 260ms; }
.s2 { left: -4%; bottom: 4%; animation-delay: 350ms; }
.s3 { right: -12%; top: -4%; animation-delay: 310ms; }
.s4 { right: 2%; top: -26%; animation-delay: 410ms; }
.s5 { right: -18%; bottom: -2%; animation-delay: 380ms; }
.over .s3, .over .s4 { animation-delay: 0ms; }

@keyframes deepen-in {
  from { opacity: 0; }
}
@keyframes letter-rise {
  0% { opacity: 0; transform: translateY(60%) scaleY(1.3); }
  100% { opacity: 1; transform: none; }
}
@keyframes letter-stamp {
  0% { opacity: 0; transform: scale(2.4) rotate(-6deg); }
  55% { opacity: 1; transform: scale(0.92); }
  80% { transform: scale(1.05); }
  100% { opacity: 1; transform: none; }
}
@keyframes label-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}
@keyframes chip-stamp {
  0% { opacity: 0; transform: scale(2); }
  100% { opacity: 1; transform: none; }
}
@keyframes band-flash {
  from { opacity: 0.85; }
  to { opacity: 0; }
}
@keyframes burst-fly {
  0% { opacity: 0; translate: -50% -50%; scale: 0.2; }
  15% { opacity: 1; }
  100% { opacity: 0; translate: calc(var(--d) - 50%) -50%; scale: 1.1; }
}
@keyframes spark-pop {
  0% { opacity: 0; transform: scale(0) rotate(-40deg); }
  60% { opacity: 1; transform: scale(1.15) rotate(8deg); }
  100% { opacity: 1; transform: scale(1) rotate(0); }
}
</style>
