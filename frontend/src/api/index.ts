import axios from "axios";
import router from "@/router";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

// 401 清理回调:由 main.ts 注入 auth store 的 logout(不直接 import store,避免 api ↔ stores 循环依赖)
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
});

// 请求拦截:带 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("sci_assistant_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截:401 -> 交给 auth store 原子清登录态(store+localStorage),再带 redirect 跳登录页。
// 登录页自身的 401(如密码错误)不清不跳,避免吞掉表单错误提示。
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && router.currentRoute.value.name !== "login") {
      onUnauthorized?.();
      router.push({ name: "login", query: { redirect: router.currentRoute.value.fullPath } });
    }
    return Promise.reject(error);
  }
);

/** 从 axios 错误中提取用户可读消息(统一错误体 {code,message,detail} 或 HTTPException detail)。 */
export function errMessage(e: unknown): string {
  const err = e as { response?: { data?: { detail?: unknown; message?: string } }; message?: string };
  const d = err?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object") {
    const msg = (d as { message?: string }).message;
    if (msg) return msg;
  }
  if (err?.response?.data?.message) return err.response.data.message;
  if (err?.message) return err.message;
  return "请求失败,请稍后重试";
}

export default api;
