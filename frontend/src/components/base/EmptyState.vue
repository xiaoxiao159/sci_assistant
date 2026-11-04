<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string;
    description?: string;
  }>(),
  { description: "" }
);
</script>

<template>
  <div class="empty">
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    <div class="empty-title">{{ title }}</div>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div class="mt-2"><slot /></div>
  </div>
</template>

<style scoped>
.empty-desc {
  font-size: var(--fs-sm);
  max-width: 360px;
}
</style>
