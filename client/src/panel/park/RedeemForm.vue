<script setup lang="ts">
// Redeem codes (protocol/PROTOCOL.md 兑换码), in the coin page's bottom bar: the field and one key on one line; why
// not, or the reward in big numbers, shows between them. Coins redeemed also rise from the top bar's coin chip.
// On a server with account login only a save linked to an account redeems, so a guest gets the sign-in instead.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Api, type ServerInfo } from "../../net/api";
import { toHttpBase } from "../../net/protocol";
import { accountLoginTrusted } from "../../net/trust";
import { activeAccount, saveCode } from "../../stores/player";
import { parkTry } from "../../stores/park";
import { settings } from "../../stores/settings";
import Icon from "../../ui/Icon.vue";
import AccountDialog from "../AccountDialog.vue";
import { COIN_SMALL } from "./coin";
import { popCoins } from "./pops";
import { redeemMessage } from "./redeem";

const code = ref("");
const busy = ref(false);
const reward = ref<{ shards: number; coins: number } | null>(null);
/** Counts rewards, so the same amount twice still pops anew. */
const rewardId = ref(0);
const error = ref("");
/** The server answered login_required, or says up front that it signs in with accounts and this device has none. */
const needLogin = ref(false);
const signingIn = ref(false);
/** When the lock after too many wrong codes ends (ms), 0 when not locked. */
const lockedUntil = ref(0);
const now = ref(Date.now());
let ticker: ReturnType<typeof setInterval> | undefined;

const info = ref<ServerInfo | null>(null);
const server = toHttpBase(settings.serverUrl);
new Api(() => server, () => saveCode.value).info().then((r) => {
  if (server !== toHttpBase(settings.serverUrl)) return;
  info.value = r;
  if (r.accountLogin && !activeAccount()) needLogin.value = true;
}).catch(() => { /* an older server without accounts: the redeem answer tells */ });
/** The account service to sign in with; null when the server or the service is not trusted. */
const mainApi = computed(() => {
  const i = info.value;
  return i?.accountLogin && i.mainApi && accountLoginTrusted(toHttpBase(settings.serverUrl), i.mainApi) ? i.mainApi : null;
});
watch(() => activeAccount()?.token, (token) => { if (token) needLogin.value = false; });

const locked = computed(() => lockedUntil.value > now.value);
const lockMinutes = computed(() => Math.max(1, Math.ceil((lockedUntil.value - now.value) / 60000)));
watch(locked, (on) => {
  if (on || !ticker) return;
  clearInterval(ticker);
  ticker = undefined;
  error.value = "";
});
onBeforeUnmount(() => clearInterval(ticker));

function lock(seconds: number) {
  lockedUntil.value = Date.now() + seconds * 1000;
  now.value = Date.now();
  ticker ??= setInterval(() => { now.value = Date.now(); }, 1000);
}

async function redeem() {
  const text = code.value.trim();
  if (!text || busy.value || locked.value) return;
  busy.value = true;
  error.value = "";
  reward.value = null;
  const r = await parkTry<{ redeemed: { shards: number; coins: number } }>("POST", "/api/redeem", { code: text });
  busy.value = false;
  if (r.ok) {
    reward.value = r.data.redeemed;
    rewardId.value++;
    code.value = "";
    if (r.data.redeemed.coins > 0) popCoins(r.data.redeemed.coins);
    return;
  }
  const e = r.error;
  if (e.code === "login_required") {
    needLogin.value = true;
    return;
  }
  if (e.code === "too_many_tries") lock(Number(e.detail.seconds) || 900);
  error.value = redeemMessage(e.code, e.message);
}
/** Typing a new code clears what the last one said. */
function typed() {
  error.value = "";
  reward.value = null;
}
const shownError = computed(() => (locked.value ? `输错太多次，${lockMinutes.value} 分钟后再试` : error.value));
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <AccountDialog v-if="signingIn && mainApi" :main-api="mainApi" start="login" @close="signingIn = false" @done="signingIn = false" />
  <div v-if="needLogin" class="redeem-bar login">
    <p class="why"><Icon name="lock" :size="16" />登录 Asasfans 账号后兑换</p>
    <button v-if="mainApi" type="button" class="ui-btn primary" @click="signingIn = true">登录</button>
  </div>
  <form v-else class="redeem-bar" @submit.prevent="redeem">
    <label class="name" for="redeem-code">兑换码</label>
    <input
      id="redeem-code" v-model="code" class="ui-input code" maxlength="64" placeholder="XXXX-XXXX-XXXX"
      autocomplete="off" autocapitalize="characters" spellcheck="false"
      @input="typed"
    />
    <p v-if="shownError" class="err" role="alert">{{ shownError }}</p>
    <p v-else-if="reward" :key="rewardId" class="got" role="status">
      <span v-if="reward.shards" :title="`碎片 +${fmt(reward.shards)}`"><Icon name="shard" :size="22" />+{{ fmt(reward.shards) }}</span>
      <span v-if="reward.coins" :title="`驼币 +${fmt(reward.coins)}`"><img :src="COIN_SMALL" alt="" draggable="false" />+{{ fmt(reward.coins) }}</span>
    </p>
    <button type="submit" class="ui-btn primary go" :disabled="!code.trim() || busy || locked" :aria-busy="busy">兑换</button>
  </form>
</template>

<style scoped>
/* One line in the page's bottom bar (.park-actions): the field takes what the rest leaves. */
.redeem-bar {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}
.name {
  flex: none;
  font: 800 var(--fs-strong)/1 var(--font);
  color: var(--ink-2);
}
.code {
  flex: 1 1 120px;
  min-width: 0;
  max-width: 360px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.code::placeholder {
  letter-spacing: 0.12em;
}
.go {
  flex: none;
  min-width: 84px;
  margin-left: auto;
}
/* The bar is already --c-100: a disabled key there takes the next step so it does not vanish. */
.go:disabled {
  --key-top: var(--c-200);
  --key-bottom: var(--c-200);
}
.err {
  min-width: 0;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  line-height: 1.3;
  color: var(--c-700);
}
/* The reward lands like the update reward: big coral numbers, popping in. */
.got {
  display: flex;
  align-items: center;
  gap: 4px 18px;
  margin: 0;
}
.got span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 800 30px/1 var(--font-latin);
  color: var(--c-700);
  animation: got-pop 520ms var(--ease-pop) both;
}
.got span + span {
  animation-delay: 90ms;
}
.got svg {
  color: var(--c-600);
}
.got img {
  width: 24px;
  height: 24px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
@keyframes got-pop {
  0% { opacity: 0; scale: 0.4; translate: 0 10px; }
  100% { opacity: 1; scale: 1; translate: 0 0; }
}
.calm .got span {
  animation: none;
}
.why {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font: 700 var(--fs-body)/1.4 var(--font);
  color: var(--ink);
}
.why svg {
  color: var(--c-700);
}
.login {
  justify-content: space-between;
}
.login .primary {
  min-width: 96px;
}

@container panel (max-width: 760px) {
  .redeem-bar {
    gap: 10px;
  }
  .code {
    max-width: none;
  }
  .got span {
    font-size: 24px;
  }
}
@container panel (max-height: 560px) {
  .go {
    height: 32px;
    min-width: 72px;
  }
  .code {
    height: 32px;
  }
}
</style>
