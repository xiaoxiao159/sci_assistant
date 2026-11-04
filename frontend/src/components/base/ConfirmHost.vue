<script setup lang="ts">
import { useUiStore } from "@/stores/ui";
import Modal from "./Modal.vue";

const ui = useUiStore();

function onCancel() {
  ui._resolveConfirm(false);
}

function onConfirm() {
  ui._resolveConfirm(true);
}
</script>

<template>
  <Modal
    v-if="ui.confirmState"
    :open="true"
    :title="ui.confirmState.title"
    width="420px"
    :close-on-mask="false"
    @close="onCancel"
  >
    <p v-if="ui.confirmState.description" class="confirm-desc">
      {{ ui.confirmState.description }}
    </p>
    <template #footer>
      <button class="btn btn-ghost" type="button" @click="onCancel">取消</button>
      <button
        class="btn"
        :class="ui.confirmState.danger ? 'btn-danger' : 'btn-primary'"
        type="button"
        @click="onConfirm"
      >
        {{ ui.confirmState.confirmText || "确认" }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.confirm-desc {
  color: var(--text-2);
  line-height: 1.7;
}
</style>
