<script setup lang="ts">
import { computed } from "vue";

type DocStatus = "uploaded" | "processing" | "ready" | "failed";
type TaskStatus = "pending" | "running" | "succeeded" | "failed";
type KbStatus = "active" | "archived";

const props = defineProps<{
  status: DocStatus | TaskStatus | KbStatus | string;
  kind?: "document" | "task" | "kb";
}>();

interface BadgeLook {
  label: string;
  cls: string;
  pulsing?: boolean;
}

const DOC: Record<string, BadgeLook> = {
  uploaded: { label: "已上传", cls: "badge-neutral" },
  processing: { label: "解析中", cls: "badge-info", pulsing: true },
  ready: { label: "已就绪", cls: "badge-success" },
  failed: { label: "失败", cls: "badge-danger" },
};

const TASK: Record<string, BadgeLook> = {
  pending: { label: "待处理", cls: "badge-neutral" },
  running: { label: "进行中", cls: "badge-info", pulsing: true },
  succeeded: { label: "已成功", cls: "badge-success" },
  failed: { label: "失败", cls: "badge-danger" },
};

const KB: Record<string, BadgeLook> = {
  active: { label: "启用中", cls: "badge-success" },
  archived: { label: "已归档", cls: "badge-neutral" },
};

const look = computed<BadgeLook>(() => {
  const table = props.kind === "task" ? TASK : props.kind === "kb" ? KB : DOC;
  return table[props.status] ?? { label: props.status, cls: "badge-neutral" };
});
</script>

<template>
  <span class="badge" :class="[look.cls, { pulsing: look.pulsing }]">
    <span class="dot" />
    {{ look.label }}
  </span>
</template>

<style scoped>
.badge.pulsing .dot {
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% { opacity: 0.35; }
}
</style>
