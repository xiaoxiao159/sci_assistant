<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import PageHeader from "@/components/base/PageHeader.vue";
import StatusBadge from "@/components/base/StatusBadge.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import LoadMore from "@/components/base/LoadMore.vue";
import TaskDetailModal from "@/components/task/TaskDetailModal.vue";
import { taskApi, type Task, type TaskStatus } from "@/api/task";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 任务中心:后台解析/索引任务的运行情况,失败可重试。 */

const PAGE_SIZE = 20;

const ui = useUiStore();

type Filter = TaskStatus | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待处理" },
  { key: "running", label: "进行中" },
  { key: "succeeded", label: "已成功" },
  { key: "failed", label: "已失败" },
];

const filter = ref<Filter>("all");
const tasks = ref<Task[]>([]);
const total = ref(0);
const loading = ref(false);
const detailId = ref<string | null>(null);

const hasMore = computed(() => tasks.value.length < total.value);

async function loadPage(reset: boolean) {
  loading.value = true;
  try {
    const page = await taskApi.list({
      status: filter.value === "all" ? undefined : filter.value,
      offset: reset ? 0 : tasks.value.length,
      limit: PAGE_SIZE,
    });
    if (reset) tasks.value = page.items;
    else tasks.value = [...tasks.value, ...page.items];
    total.value = page.total;
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    loading.value = false;
  }
}

async function switchFilter(f: Filter) {
  if (f === filter.value) return;
  filter.value = f;
  await loadPage(true);
}

onMounted(() => loadPage(true));

// 有进行中任务且页面可见时,10s 静默刷新首屏
const hasActive = computed(() => tasks.value.some((t) => t.status === "pending" || t.status === "running"));
let refreshTimer: ReturnType<typeof setInterval> | null = null;

function tickRefresh() {
  if (!hasActive.value || document.hidden || detailId.value) return;
  const offset = tasks.value.length;
  void taskApi
    .list({
      status: filter.value === "all" ? undefined : filter.value,
      offset: 0,
      limit: Math.max(offset, PAGE_SIZE),
    })
    .then((page) => {
      tasks.value = page.items;
      total.value = page.total;
    })
    .catch(() => { /* 静默刷新失败不打扰 */ });
}

onMounted(() => {
  refreshTimer = setInterval(tickRefresh, 10000);
});

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});

async function onRetried() {
  await loadPage(true);
}

const TASK_TYPES: Record<string, string> = {
  index_document: "文档索引",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <div class="page">
    <PageHeader title="任务中心" sub="文档解析与索引在后台异步执行,可在此跟踪进度与失败原因" />

    <div class="tabs">
      <button
        v-for="f in FILTERS"
        :key="f.key"
        class="tab"
        :class="{ active: filter === f.key }"
        type="button"
        @click="switchFilter(f.key)"
      >
        {{ f.label }}
      </button>
    </div>

    <div v-if="loading && !tasks.length" class="col task-list">
      <div v-for="i in 4" :key="i" class="card task-row">
        <div class="skeleton" style="height: 15px; width: 35%" />
        <div class="skeleton" style="height: 12px; width: 55%" />
      </div>
    </div>

    <EmptyState
      v-else-if="!tasks.length"
      title="暂无任务"
      :description="filter === 'all'
        ? '上传文档后,解析与索引任务会出现在这里。'
        : '当前筛选下没有任务。'"
    />

    <template v-else>
      <div class="col task-list">
        <div
          v-for="t in tasks"
          :key="t.id"
          class="card task-row"
          role="button"
          tabindex="0"
          @click="detailId = t.id"
          @keydown.enter="detailId = t.id"
        >
          <div class="task-main">
            <div class="row" style="gap: var(--sp-2); align-items: center">
              <span class="task-type">{{ TASK_TYPES[t.task_type] || t.task_type }}</span>
              <StatusBadge :status="t.status" kind="task" />
            </div>
            <div class="task-meta">
              {{ fmtTime(t.created_at) }}
              <template v-if="t.status === 'failed'">
                · 尝试 {{ t.attempt_count }}/{{ t.max_attempts }}
                <template v-if="t.error_message"> · {{ t.error_message }}</template>
              </template>
            </div>
          </div>
          <span class="task-open">详情 ›</span>
        </div>
      </div>
      <LoadMore :loading="loading" :has-more="hasMore" :total="total" @load="loadPage(false)" />
    </template>

    <TaskDetailModal
      :open="!!detailId"
      :task-id="detailId || ''"
      @close="detailId = null"
      @retried="onRetried"
    />
  </div>
</template>

<style scoped>
.page {
  padding: var(--sp-6);
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.tabs {
  display: flex;
  gap: var(--sp-1);
  margin-bottom: var(--sp-4);
  border-bottom: 1px solid var(--border);
}

.tab {
  padding: var(--sp-2) var(--sp-4);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-3);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  margin-bottom: -1px;
}

.tab:hover { color: var(--text-1); }

.tab.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
}

.task-list {
  gap: var(--sp-3);
}

.task-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  cursor: pointer;
}

.task-row:hover {
  border-color: var(--border-strong);
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-type {
  font-weight: 500;
  color: var(--text-1);
}

.task-meta {
  margin-top: 2px;
  font-size: var(--fs-xs);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-open {
  font-size: var(--fs-xs);
  color: var(--text-3);
  flex-shrink: 0;
}
</style>
