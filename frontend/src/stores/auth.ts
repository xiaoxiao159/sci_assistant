import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi, type User } from "@/api/auth";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("sci_assistant_token"));
  const user = ref<User | null>(
    JSON.parse(localStorage.getItem("sci_assistant_user") || "null")
  );

  const isLoggedIn = computed(() => !!token.value);

  function _persist() {
    if (token.value) localStorage.setItem("sci_assistant_token", token.value);
    else localStorage.removeItem("sci_assistant_token");
    if (user.value) localStorage.setItem("sci_assistant_user", JSON.stringify(user.value));
    else localStorage.removeItem("sci_assistant_user");
  }

  async function login(username: string, password: string) {
    const res = await authApi.login({ username, password });
    token.value = res.access_token;
    user.value = res.user;
    _persist();
  }

  async function register(data: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
  }) {
    const res = await authApi.register(data);
    token.value = res.access_token;
    user.value = res.user;
    _persist();
  }

  function logout() {
    token.value = null;
    user.value = null;
    _persist();
  }

  return { token, user, isLoggedIn, login, register, logout };
});
