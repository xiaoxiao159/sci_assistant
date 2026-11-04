import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { setUnauthorizedHandler } from "./api";
import { useAuthStore } from "./stores/auth";
import { useNavStore } from "./stores/nav";
import "./styles/index.css";

const app = createApp(App).use(createPinia()).use(router);
// 401 时统一清理:登录态(auth)+ 导航缓存(nav),与 AppLayout 退出按钮行为一致;
// store 在回调内惰性取,pinia 就绪后才可用
setUnauthorizedHandler(() => {
  useAuthStore().logout();
  useNavStore().invalidate();
});
app.mount("#app");
