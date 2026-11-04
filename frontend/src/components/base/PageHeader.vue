<script setup lang="ts">
defineProps<{
  title: string;
  sub?: string;
}>();
</script>

<template>
  <div class="page-head">
    <div class="flex-1">
      <div class="row">
        <slot name="back" />
        <h1>{{ title }}</h1>
      </div>
      <p v-if="sub" class="page-sub">{{ sub }}</p>
    </div>
    <div class="row">
      <slot name="actions" />
    </div>
  </div>
</template>
