<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import Modal from "../ui/Modal.vue";
import SegTabs from "../ui/SegTabs.vue";
import { Api, ApiError, type SaveSummary } from "../net/api";
import { MainAccountApi, type MainSession } from "../net/mainAccount";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { saveCode, setAccount } from "../stores/player";

const props = defineProps<{ mainApi: string; start: "login" | "register" }>();
const emit = defineEmits<{ close: []; done: [message: string] }>();

type Step = "login" | "register" | "reset" | "bind" | "choose";
const step = ref<Step>(props.start);
const main = new MainAccountApi(props.mainApi);

const account = ref("");
const username = ref("");
const email = ref("");
const code = ref("");
const password = ref("");
const confirm = ref("");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const cooldown = ref(0);
const resetSent = ref(false);
const bindSentTo = ref("");
/** Signed in on the main site, not yet active on this device. */
const pending = ref<MainSession | null>(null);
const saves = ref<{ account: SaveSummary; guest: SaveSummary } | null>(null);

let timer: ReturnType<typeof setInterval> | undefined;
onBeforeUnmount(() => clearInterval(timer));
function startCooldown() {
  cooldown.value = 60;
  clearInterval(timer);
  timer = setInterval(() => { if (--cooldown.value <= 0) clearInterval(timer); }, 1000);
}

const title = computed(() => ({
  login: "Asasfans 账号登录", register: "注册 Asasfans 账号", reset: "重设密码", bind: "绑定邮箱", choose: "选择存档",
}[step.value]));
const tabs = [{ id: "login" as const, label: "登录" }, { id: "register" as const, label: "注册" }];

async function run(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try { await action(); }
  catch (e) { error.value = e instanceof Error ? e.message : "操作没有完成，请重试"; }
  finally { busy.value = false; }
}
function switchTo(next: Step) {
  step.value = next;
  error.value = "";
  notice.value = "";
  password.value = "";
  confirm.value = "";
  code.value = "";
}

/** A signed-in account needs a verified email, then gets this device's save or a choice between two. */
async function proceed(session: MainSession) {
  pending.value = session;
  password.value = "";
  confirm.value = "";
  code.value = "";
  if (!session.user.email) { step.value = "bind"; return; }
  const server = toHttpBase(settings.serverUrl);
  try {
    const result = await new Api(() => server, () => saveCode.value).link(session.token, saveCode.value);
    await setAccount({ server, token: session.token, user: result.user }, result.linkedGuest);
    emit("done", result.linkedGuest ? `已登录 ${result.user.username}，当前存档已绑定到账号` : `已登录 ${result.user.username}`);
  } catch (e) {
    if (e instanceof ApiError && e.code === "account_has_save") {
      saves.value = { account: e.detail.account as SaveSummary, guest: e.detail.guest as SaveSummary };
      step.value = "choose";
      return;
    }
    throw e;
  }
}

const login = () => run(async () => proceed(await main.login(account.value.trim(), password.value)));
const sendSignupCode = () => run(async () => {
  await main.sendRegistrationCode(email.value.trim());
  startCooldown();
  notice.value = `验证码已发送到 ${email.value.trim()}，10 分钟内有效`;
});
const register = () => run(async () => {
  if (password.value !== confirm.value) throw new Error("两次输入的密码不一致");
  await proceed(await main.register(username.value.trim(), email.value.trim(), code.value.trim(), password.value));
});
const requestReset = () => run(async () => {
  await main.requestPasswordReset(account.value.trim());
  resetSent.value = true;
  notice.value = "如果该账号已绑定邮箱，验证码已发到邮箱";
});
const confirmReset = () => run(async () => {
  if (password.value !== confirm.value) throw new Error("两次输入的密码不一致");
  await main.confirmPasswordReset(account.value.trim(), code.value.trim(), password.value);
  resetSent.value = false;
  switchTo("login");
  notice.value = "密码已重设，请用新密码登录";
});
const sendBindCode = () => run(async () => {
  await main.sendEmailCode(pending.value!.token, email.value.trim());
  bindSentTo.value = email.value.trim();
  startCooldown();
});
const verifyBind = () => run(async () => {
  const verified = await main.verifyEmail(pending.value!.token, code.value.trim());
  await proceed({ ...pending.value!, user: { ...pending.value!.user, email: verified } });
});
const useAccountSave = () => run(async () => {
  const session = pending.value!;
  await setAccount({ server: toHttpBase(settings.serverUrl), token: session.token, user: session.user });
  emit("done", `已登录 ${session.user.username}，正在使用账号存档`);
});
const keepGuest = () => run(async () => {
  await main.revoke(pending.value!.token).catch(() => {});
  emit("done", "继续使用当前游客存档");
});

function cancel() {
  // A main-site token that never became active on this device is signed out again.
  if (pending.value) void main.revoke(pending.value.token).catch(() => {});
  emit("close");
}
const ago = (seconds: number) => new Date(seconds * 1000).toLocaleDateString("zh-CN");
</script>

<template>
  <Modal :title="title" heading @close="cancel">
    <div class="account">
      <SegTabs v-if="step === 'login' || step === 'register'" :tabs="tabs" :model-value="step" label="登录或注册" @update:model-value="switchTo" />
      <p v-if="step === 'login'" class="scope">Asasfans 账号通用于 Asasfans Web、Asasfans Next 与本桌宠。</p>
      <p v-else-if="step === 'register'" class="scope">已在 Asasfans Web 或 Asasfans Next 注册的账号可直接登录。</p>

      <Transition name="step" mode="out-in">
        <form v-if="step === 'login'" key="login" class="fields" @submit.prevent="login">
          <label><span>用户名或邮箱</span><input v-model="account" class="ui-input" autocomplete="username" required maxlength="254" /></label>
          <label>
            <span class="split">密码<button type="button" class="link" @click="switchTo('reset')">忘记密码？</button></span>
            <input v-model="password" class="ui-input" type="password" autocomplete="current-password" required minlength="8" maxlength="128" />
          </label>
          <button class="ui-btn primary large" type="submit" :disabled="busy">{{ busy ? "登录中…" : "登录" }}</button>
        </form>

        <form v-else-if="step === 'register'" key="register" class="fields" @submit.prevent="register">
          <label><span>用户名</span><input v-model="username" class="ui-input" autocomplete="username" required minlength="3" maxlength="32" placeholder="3–32 个字母、数字或 _.-" /></label>
          <label><span>邮箱</span><input v-model="email" class="ui-input" type="email" autocomplete="email" required maxlength="254" placeholder="name@example.com" /></label>
          <label>
            <span>邮箱验证码</span>
            <span class="pair">
              <input v-model="code" class="ui-input code" inputmode="numeric" autocomplete="one-time-code" required pattern="[0-9]{6}" maxlength="6" placeholder="6 位数字" />
              <button type="button" class="ui-btn" :disabled="busy || cooldown > 0 || !email.trim()" @click="sendSignupCode">{{ cooldown > 0 ? `${cooldown} 秒` : "发送验证码" }}</button>
            </span>
          </label>
          <label><span>密码</span><input v-model="password" class="ui-input" type="password" autocomplete="new-password" required minlength="8" maxlength="128" placeholder="至少 8 个字符" /></label>
          <label><span>确认密码</span><input v-model="confirm" class="ui-input" type="password" autocomplete="new-password" required minlength="8" maxlength="128" /></label>
          <button class="ui-btn primary large" type="submit" :disabled="busy">{{ busy ? "注册中…" : "注册并登录" }}</button>
        </form>

        <form v-else-if="step === 'reset'" key="reset" class="fields" @submit.prevent="resetSent ? confirmReset() : requestReset()">
          <label><span>用户名或邮箱</span><input v-model="account" class="ui-input" autocomplete="username" required maxlength="254" :readonly="resetSent" /></label>
          <template v-if="resetSent">
            <label><span>验证码</span><input v-model="code" class="ui-input code" inputmode="numeric" autocomplete="one-time-code" required pattern="[0-9]{6}" maxlength="6" placeholder="6 位数字" /></label>
            <label><span>新密码</span><input v-model="password" class="ui-input" type="password" autocomplete="new-password" required minlength="8" maxlength="128" placeholder="至少 8 个字符" /></label>
            <label><span>确认新密码</span><input v-model="confirm" class="ui-input" type="password" autocomplete="new-password" required minlength="8" maxlength="128" /></label>
          </template>
          <button class="ui-btn primary large" type="submit" :disabled="busy">{{ resetSent ? "重设密码" : "发送验证码" }}</button>
          <button type="button" class="link center" @click="resetSent = false; switchTo('login')">返回登录</button>
        </form>

        <form v-else-if="step === 'bind'" key="bind" class="fields" @submit.prevent="bindSentTo ? verifyBind() : sendBindCode()">
          <p class="lead">账号 <b>{{ pending?.user.username }}</b> 还没有绑定邮箱，绑定后才能在桌宠上使用。</p>
          <label><span>邮箱</span><input v-model="email" class="ui-input" type="email" autocomplete="email" required maxlength="254" :readonly="!!bindSentTo" /></label>
          <label v-if="bindSentTo"><span>验证码</span><input v-model="code" class="ui-input code" inputmode="numeric" autocomplete="one-time-code" required pattern="[0-9]{6}" maxlength="6" placeholder="6 位数字" /></label>
          <button class="ui-btn primary large" type="submit" :disabled="busy">{{ bindSentTo ? "完成绑定" : "发送验证码" }}</button>
          <button v-if="bindSentTo" type="button" class="link center" :disabled="cooldown > 0" @click="bindSentTo = ''">{{ cooldown > 0 ? `${cooldown} 秒后可换邮箱或重发` : "换一个邮箱或重发" }}</button>
        </form>

        <div v-else key="choose" class="fields">
          <p class="lead">账号 <b>{{ pending?.user.username }}</b> 已经有桌宠存档，这台设备上也有一份游客存档。两份都会保留，选一份现在使用：</p>
          <div class="saves">
            <button type="button" class="save ui-frame" :disabled="busy" @click="useAccountSave">
              <b>账号存档</b>
              <span>{{ saves?.account.shards.toLocaleString("en-US") }} 碎片 · 收集 {{ saves?.account.owned }}</span>
              <small>最近活跃 {{ saves ? ago(saves.account.lastActive) : "" }}</small>
            </button>
            <button type="button" class="save ui-frame" :disabled="busy" @click="keepGuest">
              <b>继续用游客存档</b>
              <span>{{ saves?.guest.shards.toLocaleString("en-US") }} 碎片 · 收集 {{ saves?.guest.owned }}</span>
              <small>不登录账号</small>
            </button>
          </div>
        </div>
      </Transition>

      <p v-if="error" class="ui-error msg" role="alert">{{ error }}</p>
      <p v-else-if="notice" class="msg ok" role="status">{{ notice }}</p>
    </div>
  </Modal>
</template>

<style scoped>
.account {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: min(380px, 100%);
  margin: 0 auto;
  padding-bottom: 6px;
}
.fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fields label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.fields .ui-input {
  height: 40px;
  background: var(--c-100);
  box-shadow: none;
}
.fields .ui-input:focus {
  box-shadow: 0 0 0 2px var(--ink);
}
.fields .ui-input[readonly] {
  color: var(--ink-2);
}
.code {
  font-family: var(--font-latin);
  letter-spacing: 0.3em;
}
.code::placeholder {
  letter-spacing: normal;
}
.pair {
  display: flex;
  gap: 8px;
}
.pair .ui-input {
  flex: 1;
}
.pair .ui-btn {
  flex: none;
  min-width: 96px;
  height: 40px;
}
.split {
  display: flex;
  justify-content: space-between;
}
.link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 700;
  color: var(--c-700);
  cursor: pointer;
}
.link:hover:not(:disabled) {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.link:disabled {
  color: var(--ink-3);
  cursor: default;
}
.center {
  align-self: center;
  font-size: var(--fs-label);
}
.fields > .ui-btn.primary {
  margin-top: 4px;
}
.scope {
  margin: -4px 0 0;
  font-size: var(--fs-label);
  line-height: 1.5;
  color: var(--ink-2);
}
.lead {
  margin: 0;
  font-size: var(--fs-body);
  line-height: 1.6;
  color: var(--ink-2);
}
.lead b {
  color: var(--ink);
}
.saves {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.save {
  --radius: var(--radius-key);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 14px;
  border: 0;
  background: var(--c-100);
  font: inherit;
  text-align: left;
  color: var(--ink);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.save:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 0 0 2px var(--c-500);
}
.save span {
  font-size: var(--fs-label);
  font-weight: 700;
}
.save small {
  font-size: var(--fs-caption);
  color: var(--ink-3);
}
.msg {
  margin: 0;
}
.ok {
  padding: 4px 10px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink);
}
.step-enter-active,
.step-leave-active {
  transition: opacity var(--dur-fast), transform var(--dur-fast) var(--ease-out);
}
.step-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.step-leave-to {
  opacity: 0;
}
</style>
