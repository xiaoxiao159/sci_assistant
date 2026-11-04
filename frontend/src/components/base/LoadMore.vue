<script setup lang="ts">
defineProps<{
  loading: boolean;
  hasMore: boolean;
  total?: number;
}>();

const emit = defineEmits<{ load: [] }>();
</script>

<template>
  <div class="load-more">
    <span v-if="total !== undefined" class="text-3 text-xs">共 {{ total }} 条</span>
    <button
      v-if="hasMore"
      class="btn btn-ghost btn-sm"
      type="button"
      :disabled="loading"
      @click="emit('load')"
    >
      <span v-if="loading" class="spinner" style="width: 14px; height: 14px" />
      {{ loading ? "加载中…" : "加载更多" }}
    </button>
    <span v-else class="text-3 text-xs">没有更多了</span>
  </div>
</template>

<style scoped>
.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-3);
  padding: var(--sp-4) 0;
}
</style>
