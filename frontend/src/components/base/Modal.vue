<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";

/** 弹窗外壳:Teleport + 遮罩 + Esc 关闭。所有弹窗的唯一基座。 */
const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    width?: string;
    closeOnMask?: boolean;
  }>(),
  { width: "520px", closeOnMask: true }
);

const emit = defineEmits<{ close: [] }>();

function onMask() {
  if (props.closeOnMask) emit("close");
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) emit("close");
}

onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <Transition name="pop">
      <div v-if="open" class="modal-mask" @mousedown.self="onMask">
        <div class="modal" :style="{ width }" role="dialog" :aria-label="title">
          <header class="modal-head">
            <h3>{{ title }}</h3>
            <button class="btn btn-icon" type="button" aria-label="关闭" @click="emit('close')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </header>
          <div class="modal-body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="modal-foot">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 8vh var(--sp-4) var(--sp-4);
  background: var(--mask);
  overflow-y: auto;
}

.modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
  max-width: calc(100vw - var(--sp-8));
  max-height: 82vh;
  display: flex;
  flex-direction: column;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--border);
}

.modal-head h3 {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.modal-body {
  padding: var(--sp-5);
  overflow-y: auto;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  border-top: 1px solid var(--border);
}
</style>
