<script setup lang="ts">
// Redeem codes (protocol/PROTOCOL.md 兑换码), on the coin page: one field and one key; the reward or why not shows
// under it.
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
import { redeemMessage } from "./redeem";

const code = ref("");
const busy = ref(false);
const reward = ref<{ shards: number; coins: number } | null>(null);
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
    code.value = "";
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
const shownError = computed(() => (locked.value ? `输错太多次，${lockMinutes.value} 分钟后再试` : error.value));
const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<template>
  <AccountDialog v-if="signingIn && mainApi" :main-api="mainApi" start="login" @close="signingIn = false" @done="signingIn = false" />
  <div class="redeem-box">
    <div v-if="needLogin" class="login">
      <p class="why"><Icon name="lock" :size="16" />登录 Asasfans 账号后兑换</p>
      <button v-if="mainApi" type="button" class="ui-btn primary" @click="signingIn = true">登录</button>
    </div>
    <form v-else class="redeem" @submit.prevent="redeem">
      <div class="row">
        <input
          v-model="code" class="ui-input code" maxlength="64" placeholder="XXXX-XXXX-XXXX"
          autocomplete="off" autocapitalize="characters" spellcheck="false" aria-label="兑换码"
          @input="error = ''"
        />
        <button type="submit" class="ui-btn primary" :disabled="!code.trim() || busy || locked" :aria-busy="busy">兑换</button>
      </div>
      <p v-if="shownError" class="err" role="alert">{{ shownError }}</p>
      <p v-else-if="reward" class="got" role="status">
        <span v-if="reward.shards"><Icon name="shard" :size="24" />+{{ fmt(reward.shards) }}<small>碎片</small></span>
        <span v-if="reward.coins"><img :src="COIN_SMALL" alt="" draggable="false" />+{{ fmt(reward.coins) }}<small>驼币</small></span>
      </p>
    </form>
  </div>
</template>

<style scoped>
.redeem,
.login {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.row {
  display: flex;
  gap: 10px;
}
.code {
  flex: 1;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.code::placeholder {
  letter-spacing: 0.12em;
}
.row .primary {
  min-width: 84px;
}
.err {
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}
/* The reward lands like the update reward: big coral numbers. */
.got {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin: 6px 0 0;
}
.got span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 800 26px/1 var(--font-latin);
  color: var(--c-700);
}
.got img {
  width: 22px;
  height: 22px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
.got small {
  align-self: flex-end;
  margin-bottom: 4px;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
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
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}
.login .primary {
  min-width: 96px;
}
</style>
