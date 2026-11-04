<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/base/Modal.vue";
import StatusBadge from "@/components/base/StatusBadge.vue";
import { taskApi, type Task } from "@/api/task";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 任务详情:信息 + 事件时间线 + 失败重试。 */
const props = defineProps<{
  open: boolean;
  taskId: string;
}>();

const emit = defineEmits<{ close: []; retried: [] }>();

const ui = useUiStore();
const loading = ref(false);
const task = ref<Task | null>(null);
const retrying = ref(false);

watch(
  () => props.open,
  async (open) => {
    if (!open) return;
    loading.value = true;
    try {
      task.value = await taskApi.get(props.taskId);
    } catch (e) {
      ui.toast(errMessage(e), "error");
    } finally {
      loading.value = false;
    }
  }
);

const TASK_TYPES: Record<string, string> = {
  index_document: "文档索引",
};

async function retry() {
  if (!task.value) return;
  const ok = await ui.confirm({
    title: "重试此任务?",
    description: "将重新执行该任务,已完成的处理不会重复。",
    confirmText: "重试",
  });
  if (!ok) return;
  retrying.value = true;
  try {
    task.value = await taskApi.retry(props.taskId);
    ui.toast("已重新入队", "success");
    emit("retried");
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    retrying.value = false;
  }
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <Modal :open="open" title="任务详情" width="600px" @close="emit('close')">
    <div v-if="loading" class="col">
      <div class="skeleton" style="height: 14px" />
      <div class="skeleton" style="height: 14px; width: 70%" />
    </div>
    <template v-else-if="task">
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">类型</span>
          <span>{{ TASK_TYPES[task.task_type] || task.task_type }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">状态</span>
          <StatusBadge :status="task.status" kind="task" />
        </div>
        <div class="info-item">
          <span class="info-label">尝试次数</span>
          <span class="mono">{{ task.attempt_count }} / {{ task.max_attempts }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">创建时间</span>
          <span>{{ fmt(task.created_at) }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">开始</span>
          <span>{{ fmt(task.started_at) }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">结束</span>
          <span>{{ fmt(task.finished_at) }}</span>
        </div>
      </div>

      <div v-if="task.error_message" class="error-box">
        <div class="text-xs" style="font-weight: 600; margin-bottom: 4px">失败原因</div>
        <div class="text-sm">{{ task.error_message }}</div>
      </div>

      <div class="mt-4">
        <div class="text-xs text-3 mb-2">事件时间线</div>
        <div class="timeline">
          <div v-for="ev in task.events || []" :key="ev.id" class="tl-item">
            <span class="tl-dot" :class="`tl-${ev.status}`" />
            <div class="flex-1">
              <div class="row between">
                <span class="text-sm" style="font-weight: 500">{{ ev.status }}</span>
                <span class="text-xs text-3">{{ fmt(ev.created_at) }}</span>
              </div>
              <div v-if="ev.detail" class="text-xs text-2">{{ ev.detail }}</div>
            </div>
          </div>
          <div v-if="!(task.events || []).length" class="text-xs text-3">暂无事件记录。</div>
        </div>
      </div>

      <div v-if="task.status === 'failed' && task.attempt_count < task.max_attempts" class="mt-4">
        <button class="btn btn-accent" type="button" :disabled="retrying" @click="retry">
          {{ retrying ? "入队中…" : "重试任务" }}
        </button>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--fs-sm);
}

.info-label {
  font-size: var(--fs-xs);
  color: var(--text-3);
}

.error-box {
  margin-top: var(--sp-4);
  padding: var(--sp-3);
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  border-radius: var(--r-md);
  color: var(--danger);
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.tl-item {
  display: flex;
  gap: var(--sp-3);
}

.tl-dot {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--text-3);
  flex-shrink: 0;
}

.tl-dot.tl-succeeded { background: var(--success); }
.tl-dot.tl-failed { background: var(--danger); }
.tl-dot.tl-running { background: var(--info); }
</style>
