import { defineStore } from "pinia";
import { ref } from "vue";

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmText?: string;
  danger?: boolean;
}

let _toastId = 0;
let _confirmResolve: ((v: boolean) => void) | null = null;

/** UI 全局态:主题、toast、确认弹窗。 */
export const useUiStore = defineStore("ui", () => {
  const theme = ref<"light" | "dark">(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light"
  );
  const toasts = ref<Toast[]>([]);
  const confirmState = ref<ConfirmOptions | null>(null);

  function setTheme(t: "light" | "dark") {
    theme.value = t;
    document.documentElement.dataset.theme = t;
    localStorage.setItem("sci_assistant_theme", t);
  }

  function toggleTheme() {
    setTheme(theme.value === "dark" ? "light" : "dark");
  }

  function toast(message: string, type: ToastType = "info", duration?: number) {
    const id = ++_toastId;
    toasts.value.push({ id, message, type });
    // 错误停 6s 给足阅读时间,其余 3.5s
    const ttl = duration ?? (type === "error" ? 6000 : 3500);
    setTimeout(() => dismissToast(id), ttl);
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  /** 全局确认弹窗:resolve(true) = 用户确认。 */
  function confirm(opts: ConfirmOptions): Promise<boolean> {
    confirmState.value = opts;
    return new Promise((resolve) => {
      _confirmResolve = resolve;
    });
  }

  function _resolveConfirm(v: boolean) {
    confirmState.value = null;
    _confirmResolve?.(v);
    _confirmResolve = null;
  }

  return { theme, toasts, confirmState, setTheme, toggleTheme, toast, dismissToast, confirm, _resolveConfirm };
});
