<script setup lang="ts">
// 排行: the own namecard as others see it, editable in place, then the server-wide collection board once it loads:
// the top three as their pets standing on a podium, the rest as rows, ranked by collection score.
import { computed, onActivated, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { characters } from "../characters";
import { characterColor, getCard, manifest, memberOf, type ManifestCard } from "../manifest";
import { collectionProgress } from "../items";
import type { Board, BoardPointKind, BoardRow } from "../net/api";
import { MAX_SHOWCASE } from "../net/protocol";
import { activeAccount, collection, loadBoard } from "../stores/player";
import { shownNick } from "../stores/room";
import { settings } from "../stores/settings";
import NamePill from "../pet/NamePill.vue";
import NamePlate from "../pet/NamePlate.vue";
import { allPlates, getPlate, plateSize, plateUnlocked } from "../pet/plates";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import CardAlbum from "./CardAlbum.vue";
import CardDetail from "./CardDetail.vue";
import ProfileCard from "./ProfileCard.vue";
import PetBust from "./PetBust.vue";
import ProfileDialog from "./ProfileDialog.vue";

const pageActive = usePageActive();
const name = computed(() => settings.nick.trim() || "匿名小面包");
const color = computed(() => characterColor(settings.character));
const plate = computed(() => getPlate(settings.plate));
const showcase = computed(() => settings.showcase.map((id) => getCard(id)).filter((c): c is ManifestCard => !!c));
const progress = computed(() => collectionProgress(collection.owned));

/** A card opened from the namecard: the plate's card or a showcase card, both owned. */
const viewing = ref<ManifestCard | null>(null);
/** The picker in front of the page. */
const editing = ref<"plate" | "card" | null>(null);

/** Plates in the picker: the unlocked ones, at the backpack's size. */
const PLATE = plateSize(0.8);
const plates = computed(() => allPlates().filter((p) => plateUnlocked(p.id, collection.owned)));
function choosePlate(id: string) {
  settings.plate = id;
  editing.value = null;
}
/** Owned cards not on show yet; the album lists hidden cards first. */
const pickable = computed(() => manifest.cards.filter((c) => !settings.showcase.includes(c.id)));
function chooseCard(card: ManifestCard) {
  if (!settings.showcase.includes(card.id) && settings.showcase.length < MAX_SHOWCASE) {
    settings.showcase = [...settings.showcase, card.id];
  }
  editing.value = null;
}
function dropCard(card: ManifestCard) {
  settings.showcase = settings.showcase.filter((id) => id !== card.id);
}

// The board: undefined while the first answer is out, null from a server without one or none at all.
const board = ref<Board | null | undefined>(undefined);
const REFRESH_MS = 10_000;
let asked = 0;
let loadedAt = 0;
async function refresh(force = false) {
  if (!force && Date.now() - loadedAt < REFRESH_MS) return;
  const n = ++asked;
  const b = await loadBoard();
  if (n !== asked) return;
  // A server from before the collection score answers without `points` or scores: no board then.
  board.value = b?.points ? b : null;
  loadedAt = Date.now();
}
onActivated(() => void refresh());
watch(() => activeAccount()?.token, () => void refresh(true));

const me = computed(() => board.value?.me ?? null);
const isMine = (r: BoardRow) => me.value?.rank != null && r.rank === me.value.rank;
const mineListed = computed(() => (board.value?.cards ?? []).some(isMine));
/** Others' nicks and plates follow the room settings; the own row shows as on the profile. */
const rowNick = (r: BoardRow) => (isMine(r) ? name.value : shownNick(r));
const rowPlate = (r: BoardRow) => (isMine(r) ? settings.plate || null : settings.showPlates ? r.plate : null);
const rankFrame = (rank: number | null) => (rank === 1 ? "frame-gold" : rank && rank <= 3 ? "frame-rose" : "");
/** Why the own save has no rank: off the board by choice, no account, or not counted yet. */
const offText = computed(() => {
  const off = me.value?.off;
  return off === "hidden" ? "已在设置里关闭上榜" : off === "account" ? "登录 Asasfans 后上榜" : "稍后上榜";
});
const opened = ref<BoardRow | null>(null);
function openRow(r: BoardRow) {
  if (!isMine(r)) opened.value = r;
}
const podium = computed(() => (board.value?.cards ?? []).slice(0, 3));
const rest = computed(() => (board.value?.cards ?? []).slice(3));
const bustOf = (character: string) => (characters[character] ?? characters[memberOf(character)])?.bg ?? "";
/** The points table behind the info button, in reading order; kinds the server does not send are left out. */
const POINT_ROWS: [BoardPointKind, string][] = [
  ["big", "大隐藏"], ["skin", "皮肤"], ["epic", "史诗卡（含小隐藏）"], ["card", "普通卡"],
  ["emoteRare", "稀有表情"], ["emoteScratch", "阿草表情"], ["emoteUncommon", "罕见表情"], ["emote", "普通表情"],
];
const pointRows = computed(() =>
  POINT_ROWS.flatMap(([kind, label]) => {
    const points = board.value?.points?.[kind];
    return points == null ? [] : [{ kind, label, points }];
  }));
const showingPoints = ref(false);
const scoreText = (score: number) => score.toLocaleString("en-US");
</script>

<template>
  <div class="ui-sections">
    <ProfileCard
      data-rise :plate="plate" :name="name" :character="settings.character" :showcase="showcase" :progress="progress"
      editable :swappable="plates.length > 0"
      @open="viewing = $event" @swap="editing = 'plate'" @pick="editing = 'card'" @drop="dropCard"
    />

    <section v-if="board" data-rise>
      <h4 class="ui-label">
        <span>全服收藏榜</span>
        <button type="button" class="ui-btn ghost small points-btn" title="收藏分" aria-label="收藏分" @click="showingPoints = true">
          <Icon name="info" :size="15" />
        </button>
      </h4>
      <ol v-if="podium.length" class="podium">
        <li v-for="r in podium" :key="r.id" :class="`at${r.rank}`">
          <component
            :is="isMine(r) ? 'div' : 'button'" class="stand" :class="{ mine: isMine(r) }"
            v-bind="isMine(r) ? {} : { type: 'button', title: `${rowNick(r)}的主页` }" @click="openRow(r)"
          >
            <span class="figure">
              <Icon v-if="r.rank === 1" class="crown" name="crown" :size="24" />
              <PetBust v-if="bustOf(r.character)" class="figure-bust" :src="bustOf(r.character)" detail />
            </span>
            <span class="block">
              <span class="lid" :class="rankFrame(r.rank)" aria-hidden="true"></span>
              <b class="no">{{ r.rank }}</b>
              <span class="tag">
                <NamePlate
                  v-if="rowPlate(r)" :card="rowPlate(r)!" :nick="rowNick(r)" :color="characterColor(r.character)"
                  :width="PLATE.width" :height="PLATE.height" still
                />
                <NamePill v-else :nick="rowNick(r)" :color="characterColor(r.character)" :width="PLATE.width" />
              </span>
              <span class="score">
                <span v-if="r.big" class="big" title="大隐藏"><Icon name="crown" :size="13" />{{ r.big }}</span>
                <span v-if="r.skins" class="skins" title="皮肤"><Icon name="shirt" :size="13" />{{ r.skins }}</span>
                <b>{{ scoreText(r.score) }}</b><small>分</small>
                <em v-if="isMine(r)" class="ui-tag">我</em>
              </span>
            </span>
          </component>
        </li>
      </ol>
      <p v-else class="ui-empty">暂无</p>

      <div v-if="me && !mineListed" class="row mine own">
        <span class="rank">{{ me.rank ?? "—" }}</span>
        <CharacterAvatar class="avatar" :character="settings.character" :size="32" />
        <span class="who">
          <NamePlate v-if="plate" :card="plate.id" :nick="name" :color="color" :width="PLATE.width" :height="PLATE.height" still />
          <NamePill v-else :nick="name" :color="color" :width="PLATE.width" />
          <em class="ui-tag">我</em>
        </span>
        <span v-if="me.rank" class="score">
          <span v-if="me.big" class="big" title="大隐藏"><Icon name="crown" :size="13" />{{ me.big }}</span>
          <span v-if="me.skins" class="skins" title="皮肤"><Icon name="shirt" :size="13" />{{ me.skins }}</span>
          <b>{{ scoreText(me.score) }}</b><small>分</small>
        </span>
        <span v-else class="off">{{ offText }}</span>
      </div>

      <ol v-if="rest.length" class="rows ui-group ui-frame">
        <li v-for="r in rest" :key="r.id">
          <component
            :is="isMine(r) ? 'div' : 'button'" class="row" :class="{ mine: isMine(r) }"
            v-bind="isMine(r) ? {} : { type: 'button', title: `${rowNick(r)}的主页` }" @click="openRow(r)"
          >
            <span class="rank">{{ r.rank }}</span>
            <CharacterAvatar class="avatar" :character="r.character" :size="32" />
            <span class="who">
              <NamePlate
                v-if="rowPlate(r)" :card="rowPlate(r)!" :nick="rowNick(r)" :color="characterColor(r.character)"
                :width="PLATE.width" :height="PLATE.height" still
              />
              <NamePill v-else :nick="rowNick(r)" :color="characterColor(r.character)" :width="PLATE.width" />
              <em v-if="isMine(r)" class="ui-tag">我</em>
            </span>
            <span class="score">
              <span v-if="r.big" class="big" title="大隐藏"><Icon name="crown" :size="13" />{{ r.big }}</span>
              <span v-if="r.skins" class="skins" title="皮肤"><Icon name="shirt" :size="13" />{{ r.skins }}</span>
              <b>{{ scoreText(r.score) }}</b><small>分</small>
            </span>
          </component>
        </li>
      </ol>

    </section>

    <CardDetail v-if="viewing" :card="viewing" @close="viewing = null" />
    <Modal v-if="editing === 'plate'" title="换铭牌" heading wide @close="editing = null">
      <div class="plate-grid">
        <button type="button" class="plate-card ui-tile" :class="{ picked: !settings.plate }" @click="choosePlate('')">
          <span class="plate-well ui-frame"><NamePill :nick="name" :color="color" :width="PLATE.width" /></span>
          <b class="ui-tile-name">
            不使用铭牌
            <span v-if="!settings.plate" class="badge" aria-label="当前使用"><Icon name="check" :size="9" /></span>
          </b>
        </button>
        <button
          v-for="p in plates" :key="p.id" type="button" class="plate-card ui-tile" :class="{ picked: settings.plate === p.id }"
          @click="choosePlate(p.id)"
        >
          <span class="plate-well ui-frame">
            <NamePlate :card="p.id" :nick="name" :color="color" :width="PLATE.width" :height="PLATE.height" :still="!pageActive" />
          </span>
          <b class="ui-tile-name">
            <i v-if="p.kind === 'card'" :style="{ background: characterColor(p.card.characters[0]!) }" aria-hidden="true"></i>{{ p.name }}
            <span v-if="settings.plate === p.id" class="badge" aria-label="当前使用"><Icon name="check" :size="9" /></span>
          </b>
        </button>
      </div>
    </Modal>
    <Modal v-else-if="editing === 'card'" title="选展示卡" heading wide @close="editing = null">
      <div class="card-pick"><CardAlbum :cards="pickable" filter="owned" @inspect="chooseCard" /></div>
    </Modal>
    <Modal v-if="showingPoints" title="收藏分" heading @close="showingPoints = false">
      <table class="points"><tbody>
        <tr v-for="p in pointRows" :key="p.kind"><td>{{ p.label }}</td><td>{{ p.points }} 分</td></tr>
      </tbody></table>
    </Modal>
    <ProfileDialog v-if="opened" :key="opened.id" :row="opened" @close="opened = null" />
  </div>
</template>

<style scoped>
/* The podium: second, first, third from the left; each pet stands on its block like an acrylic stand. */
.podium {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: end;
  gap: 14px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}
.podium .at1 { order: 2; }
.podium .at2 { order: 1; }
.podium .at3 { order: 3; }
.stand {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: var(--ink);
}
button.stand {
  cursor: pointer;
}
.figure {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: -2px;
  transition: transform var(--dur-base) var(--ease-out);
}
button.stand:hover .figure {
  transform: translateY(-4px);
}
.figure-bust {
  display: block;
  width: 110px;
  height: 100px;
  filter: var(--sticker-lg);
}
.at1 .figure-bust {
  width: 132px;
  height: 120px;
}
.crown {
  color: var(--gold);
  margin-bottom: -4px;
}
.block {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 18px 10px 16px;
  overflow: hidden;
  border-radius: var(--radius-l) var(--radius-l) var(--radius-m) var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.at1 .block { min-height: 168px; }
.at2 .block { min-height: 146px; }
.at3 .block { min-height: 132px; }
.stand.mine .block {
  box-shadow: inset 0 0 0 2px var(--c-500), var(--shadow-paper);
}
/* The lid: the podium's metal, gold for first and coral for second and third. */
.lid {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 8px;
  background: var(--frame-fill, var(--c-200)) var(--frame-at, 0 0) / var(--frame-size, auto);
}
.no {
  font: 800 40px/1 var(--font-latin);
  color: var(--c-700);
}
.at1 .no {
  font-size: 48px;
  color: color-mix(in oklab, var(--gold) 70%, var(--ink));
}
.tag {
  max-width: 100%;
  display: flex;
  justify-content: center;
  overflow: hidden;
}

.rows {
  margin: 0;
}
.row {
  width: 100%;
  display: grid;
  grid-template-columns: 30px 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 50px;
  padding: 7px 18px 7px 12px;
  box-sizing: border-box;
  border: 0;
  background: none;
  font: inherit;
  color: var(--ink);
  text-align: left;
}
button.row {
  cursor: pointer;
  transition: background var(--dur-fast);
}
button.row:hover {
  background: color-mix(in srgb, var(--c-100) 45%, var(--surface));
}
.row.mine {
  background: color-mix(in srgb, var(--c-100) 70%, var(--surface));
}
.rank {
  text-align: center;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink-3);
}
.avatar {
  border-radius: 50%;
}
.who {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.who > :first-child {
  flex: none;
}
.score {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 4px;
  white-space: nowrap;
}
.score b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.block .score b {
  font-size: 24px;
}
/* Room for the widest score, so the counts before it line up from row to row. */
.row .score b {
  min-width: 4.6ch;
  text-align: right;
}
.score small {
  font: 700 var(--fs-caption)/1 var(--font-latin);
  color: var(--ink-3);
}
.score .ui-tag {
  margin-left: 6px;
}
/* Big hidden cards and skins: small tinted capsules ahead of the score. */
.big,
.skins {
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  padding: 0 8px 0 6px;
  box-sizing: border-box;
  border-radius: 10px;
  font: 800 var(--fs-label)/1 var(--font-latin);
}
.big {
  background: color-mix(in oklab, var(--gold) 16%, var(--surface));
  color: color-mix(in oklab, var(--gold) 70%, var(--ink));
}
.big svg {
  color: var(--gold);
}
.skins {
  background: var(--c-100);
  color: var(--c-700);
}
.score > b {
  margin-left: 6px;
}
.off {
  grid-column: 4 / -1;
  justify-self: end;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
/* The own rank, when it is off the podium and the rows, right under the podium. */
.own {
  margin-bottom: 14px;
  border-radius: var(--radius-l);
  box-shadow: var(--shadow-paper), inset 0 0 0 2px var(--c-300);
}
.points-btn {
  align-self: center;
  width: 28px;
  margin: -6px 0;
  padding: 0;
}
.points {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
.points td {
  padding: 10px 6px;
  border-bottom: 1px solid var(--c-100);
}
.points td:last-child {
  text-align: right;
  font: 800 var(--fs-body) var(--font-latin);
}

/* The pickers: the backpack's plate tiles, and the album limited to owned cards. */
.plate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
  gap: 10px;
}
.plate-card {
  --radius: var(--radius-m);
}
.plate-well {
  width: 100%;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-100);
}
.plate-card.picked .plate-well {
  outline: 2px solid var(--c-500);
  outline-offset: -2px;
}
.plate-well > :first-child {
  transition: transform var(--dur-base) var(--ease-out);
}
.plate-card:hover .plate-well > :first-child {
  transform: translateY(-2px);
}
.plate-card .ui-tile-name {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  margin-top: 4px;
  font: 800 var(--fs-label) var(--font);
}
.plate-card .ui-tile-name i {
  flex: none;
  width: 4px;
  height: 11px;
}
.badge {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--c-500);
  color: var(--ink);
}
.card-pick {
  height: min(440px, calc(100cqh - 140px));
  display: flex;
  flex-direction: column;
}
</style>
