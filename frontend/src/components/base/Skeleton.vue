<script setup lang="ts">
withDefaults(
  defineProps<{
    lines?: number;
    variant?: "text" | "card" | "list";
  }>(),
  { lines: 3, variant: "text" }
);
</script>

<template>
  <!-- 列表骨架 -->
  <div v-if="variant === 'list'" class="sk-list">
    <div v-for="i in lines" :key="i" class="sk-row">
      <div class="skeleton sk-avatar" />
      <div class="col flex-1">
        <div class="skeleton sk-line" :style="{ width: 40 + ((i * 13) % 40) + '%' }" />
        <div class="skeleton sk-line short" />
      </div>
    </div>
  </div>
  <!-- 卡片网格骨架 -->
  <div v-else-if="variant === 'card'" class="sk-cards">
    <div v-for="i in lines" :key="i" class="card sk-card">
      <div class="skeleton sk-line" style="width: 55%" />
      <div class="skeleton sk-line short" />
      <div class="skeleton sk-line short" style="width: 70%" />
    </div>
  </div>
  <!-- 文本行骨架 -->
  <div v-else class="col">
    <div
      v-for="i in lines"
      :key="i"
      class="skeleton sk-line"
      :style="{ width: i === lines ? '60%' : '100%' }"
    />
  </div>
</template>

<style scoped>
.sk-line {
  height: 14px;
}

.sk-line.short {
  width: 45%;
}

.sk-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
}

.sk-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--r-full);
  flex-shrink: 0;
}

.sk-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--sp-4);
}

.sk-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-4);
}
</style>
