<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

withDefaults(
  defineProps<{
    align?: "left" | "right";
  }>(),
  { align: "right" }
);

const open = ref(false);
const rootEl = ref<HTMLElement | null>(null);

function onDocClick(e: MouseEvent) {
  if (rootEl.value && !rootEl.value.contains(e.target as Node)) {
    open.value = false;
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") open.value = false;
}

onMounted(() => {
  document.addEventListener("mousedown", onDocClick);
  document.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("mousedown", onDocClick);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <div ref="rootEl" class="dropdown">
    <div class="trigger" @click="open = !open">
      <slot name="trigger" />
    </div>
    <Transition name="pop">
      <div v-if="open" class="menu" :class="`menu-${align}`" @click="open = false">
        <slot name="menu" />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.dropdown {
  position: relative;
}

.trigger {
  cursor: pointer;
}

.menu {
  position: absolute;
  top: calc(100% + var(--sp-1));
  z-index: 50;
  min-width: 160px;
  padding: var(--sp-1);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
}

.menu-right { right: 0; }
.menu-left { left: 0; }

.menu :deep(.menu-item) {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--text-2);
  background: none;
  border: none;
  border-radius: var(--r-sm);
  cursor: pointer;
  text-align: left;
}

.menu :deep(.menu-item:hover) {
  background: var(--surface-2);
  color: var(--text-1);
}

.menu :deep(.menu-item.danger) {
  color: var(--danger);
}

.menu :deep(.menu-item.danger:hover) {
  background: var(--danger-soft);
}

.menu :deep(.menu-sep) {
  height: 1px;
  margin: var(--sp-1) 0;
  background: var(--border);
}
</style>
