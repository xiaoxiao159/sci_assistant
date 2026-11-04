<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { errMessage } from "@/api";

/** 登录(用户名或邮箱)+注册。无用户类型 —— 这是科研助手。 */
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const mode = ref<"login" | "register">("login");
const busy = ref(false);

const loginForm = reactive({ login: "", password: "" });
const regForm = reactive({
  username: "",
  email: "",
  display_name: "",
  password: "",
  confirm: "",
});

function goAfterLogin() {
  const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
  // 优先带回跳地址;否则回到上次的项目/会话位置
  router.replace(redirect && redirect.startsWith("/") ? redirect : "/");
}

async function doLogin() {
  if (!loginForm.login.trim() || !loginForm.password) {
    return;
  }
  busy.value = true;
  try {
    await auth.login(loginForm.login.trim(), loginForm.password);
    goAfterLogin();
  } catch (e) {
    loginError.value = errMessage(e);
  } finally {
    busy.value = false;
  }
}

const loginError = ref("");

async function doRegister() {
  regError.value = "";
  if (!regForm.username.trim()) return (regError.value = "请填写用户名");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(regForm.email.trim()))
    return (regError.value = "请填写有效的邮箱地址");
  if (regForm.password.length < 8) return (regError.value = "密码至少 8 位");
  if (regForm.password !== regForm.confirm) return (regError.value = "两次输入的密码不一致");
  busy.value = true;
  try {
    await auth.register({
      username: regForm.username.trim(),
      email: regForm.email.trim(),
      password: regForm.password,
      display_name: regForm.display_name.trim() || undefined,
    });
    goAfterLogin();
  } catch (e) {
    regError.value = errMessage(e);
  } finally {
    busy.value = false;
  }
}

const regError = ref("");

function switchMode(m: "login" | "register") {
  mode.value = m;
  loginError.value = "";
  regError.value = "";
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <div class="brand-mark">研</div>
      <h1 class="brand-title">科研问答助手</h1>
      <p class="brand-sub">基于知识库的科研问答,回答附引用、可溯源。</p>

      <div class="card auth-card">
        <div class="tabs">
          <button
            class="tab"
            type="button"
            :class="{ active: mode === 'login' }"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            class="tab"
            type="button"
            :class="{ active: mode === 'register' }"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <!-- 登录 -->
        <form v-if="mode === 'login'" class="col" @submit.prevent="doLogin">
          <div class="field">
            <label class="label" for="login-account">用户名或邮箱</label>
            <input
              id="login-account"
              v-model="loginForm.login"
              class="input"
              autocomplete="username"
              placeholder="demo / you@lab.edu"
            />
          </div>
          <div class="field">
            <label class="label" for="login-pw">密码</label>
            <input
              id="login-pw"
              v-model="loginForm.password"
              class="input"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
            />
          </div>
          <p v-if="loginError" class="form-error">{{ loginError }}</p>
          <button class="btn btn-primary btn-block" type="submit" :disabled="busy">
            {{ busy ? "登录中…" : "登录" }}
          </button>
        </form>

        <!-- 注册 -->
        <form v-else class="col" @submit.prevent="doRegister">
          <div class="field">
            <label class="label" for="reg-username">用户名 *</label>
            <input id="reg-username" v-model="regForm.username" class="input" maxlength="64" autocomplete="username" placeholder="用于登录,如 zhangsan" />
          </div>
          <div class="field">
            <label class="label" for="reg-email">邮箱 *</label>
            <input id="reg-email" v-model="regForm.email" class="input" type="email" maxlength="255" autocomplete="email" placeholder="you@lab.edu" />
          </div>
          <div class="field">
            <label class="label" for="reg-display">显示名称</label>
            <input id="reg-display" v-model="regForm.display_name" class="input" maxlength="128" placeholder="选填,聊天界面展示用" />
          </div>
          <div class="field">
            <label class="label" for="reg-pw">密码 *</label>
            <input id="reg-pw" v-model="regForm.password" class="input" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" />
          </div>
          <div class="field">
            <label class="label" for="reg-pw2">确认密码 *</label>
            <input id="reg-pw2" v-model="regForm.confirm" class="input" type="password" minlength="8" autocomplete="new-password" placeholder="再输入一次" />
          </div>
          <p v-if="regError" class="form-error">{{ regError }}</p>
          <button class="btn btn-primary btn-block" type="submit" :disabled="busy">
            {{ busy ? "注册中…" : "创建账号" }}
          </button>
        </form>
      </div>

      <p class="foot-hint">本地部署 · 数据保存在你自己的服务器上</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(1200px 600px at 85% -10%, var(--accent-soft), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, var(--brand-soft), transparent 55%),
    var(--bg);
  padding: var(--sp-6) var(--sp-4);
}

.auth-panel {
  width: 400px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.brand-mark {
  width: 56px;
  height: 56px;
  border-radius: var(--r-lg);
  background: var(--brand);
  color: var(--bg);
  font-size: 26px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-2);
}

.brand-title {
  margin: var(--sp-4) 0 0;
  font-size: var(--fs-xl);
  font-weight: 700;
  color: var(--text-1);
}

.brand-sub {
  margin: var(--sp-2) 0 var(--sp-6);
  font-size: var(--fs-sm);
  color: var(--text-3);
  text-align: center;
}

.auth-card {
  width: 100%;
  padding: var(--sp-5);
}

.tabs {
  display: flex;
  gap: var(--sp-1);
  margin-bottom: var(--sp-4);
  border-bottom: 1px solid var(--border);
}

.tab {
  flex: 1;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-3);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  margin-bottom: -1px;
}

.tab:hover { color: var(--text-1); }

.tab.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
}

.form-error {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--danger);
}

.foot-hint {
  margin-top: var(--sp-5);
  font-size: var(--fs-xs);
  color: var(--text-3);
}
</style>
