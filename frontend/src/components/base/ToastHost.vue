<script setup lang="ts">
import { useUiStore } from "@/stores/ui";

const ui = useUiStore();
</script>

<template>
  <Teleport to="body">
    <div class="toast-host" aria-live="polite">
      <TransitionGroup name="pop">
        <div
          v-for="t in ui.toasts"
          :key="t.id"
          class="toast"
          :class="`toast-${t.type}`"
          @click="ui.dismissToast(t.id)"
        >
          <svg v-if="t.type === 'success'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
          <svg v-else-if="t.type === 'error'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
          <svg v-else-if="t.type === 'warning'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 20h16a2 2 0 0 0 1.73-2Z"/><path d="M12 9v4M12 17h.01"/></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
          <span class="toast-msg">{{ t.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: var(--sp-5);
  right: var(--sp-5);
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  max-width: 420px;
  padding: var(--sp-2) var(--sp-4);
  font-size: var(--fs-sm);
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--info);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
  cursor: pointer;
  pointer-events: auto;
}

.toast-success { border-left-color: var(--success); color: var(--success); }
.toast-error { border-left-color: var(--danger); color: var(--danger); }
.toast-warning { border-left-color: var(--warning); color: var(--warning); }
.toast-info { color: var(--info); }

.toast-msg {
  color: var(--text-1);
}
</style>
