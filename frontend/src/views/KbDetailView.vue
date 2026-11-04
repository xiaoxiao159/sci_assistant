<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  FileText,
  FileSpreadsheet,
  FileCode2,
  File as FileIcon,
  ChevronLeft,
} from "lucide-vue-next";
import PageHeader from "@/components/base/PageHeader.vue";
import StatusBadge from "@/components/base/StatusBadge.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import KbFormModal from "@/components/kb/KbFormModal.vue";
import UploadModal from "@/components/kb/UploadModal.vue";
import DocPreviewModal from "@/components/kb/DocPreviewModal.vue";
import { kbApi, type Kb } from "@/api/kb";
import { documentApi, type Document } from "@/api/document";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 知识库详情:文档管理 + 解析状态退避轮询。 */
const route = useRoute();
const router = useRouter();
const ui = useUiStore();

const kbId = computed(() => String(route.params.kbId));

const kb = ref<Kb | null>(null);
const docs = ref<Document[]>([]);
const loading = ref(true);
const loadError = ref("");

const showEdit = ref(false);
const showUpload = ref(false);
const previewDoc = ref<Document | null>(null);

// ---- 加载 ----
async function loadKb() {
  try {
    kb.value = await kbApi.get(kbId.value);
  } catch (e) {
    loadError.value = errMessage(e);
    ui.toast(loadError.value, "error");
  }
}

async function loadDocs(): Promise<Document[]> {
  try {
    docs.value = await documentApi.list(kbId.value);
    return docs.value;
  } catch (e) {
    ui.toast(errMessage(e), "error");
    return [];
  }
}

async function initialLoad() {
  loading.value = true;
  await loadKb();
  await loadDocs();
  loading.value = false;
  scheduleNext();
}

onMounted(initialLoad);

// ---- 退避轮询:2s→3s→5s→8s 封顶 10s;约 3 分钟后放弃;有状态跃迁时提示 ----
const POLL_DELAYS = [2000, 3000, 5000, 8000, 10000];
const POLL_BUDGET_MS = 3 * 60 * 1000;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollIndex = 0;
let pollElapsed = 0;

function hasPending(list: Document[]): boolean {
  return list.some((d) => d.status === "uploaded" || d.status === "processing");
}

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

function scheduleNext() {
  stopPolling();
  if (!hasPending(docs.value)) {
    pollIndex = 0;
    pollElapsed = 0;
    return;
  }
  if (pollElapsed >= POLL_BUDGET_MS) {
    ui.toast("仍有文档在解析,已暂停自动刷新,可手动刷新查看", "warning");
    pollIndex = 0;
    pollElapsed = 0;
    return;
  }
  const delay = POLL_DELAYS[Math.min(pollIndex, POLL_DELAYS.length - 1)];
  pollTimer = setTimeout(pollOnce, delay);
}

async function pollOnce() {
  const before = new Map(docs.value.map((d) => [d.id, d.status]));
  const fresh = await loadDocs();
  for (const d of fresh) {
    const prev = before.get(d.id);
    if (prev && prev !== d.status) {
      if (d.status === "ready") ui.toast(`「${d.title}」解析完成,已可检索`, "success");
      else if (d.status === "failed") ui.toast(`「${d.title}」解析失败:${d.error_message || "未知原因"}`, "error");
    }
  }
  pollIndex += 1;
  pollElapsed += POLL_DELAYS[Math.min(pollIndex, POLL_DELAYS.length - 1)];
  scheduleNext();
}

onBeforeUnmount(stopPolling);

// ---- 操作 ----
async function refreshAll() {
  await Promise.all([loadKb(), loadDocs()]);
  pollIndex = 0;
  pollElapsed = 0;
  scheduleNext();
}

async function removeKb() {
  if (!kb.value) return;
  const ok = await ui.confirm({
    title: `删除知识库「${kb.value.name}」?`,
    description: "将同时删除其下所有文档、切片与向量索引,不可恢复。",
    confirmText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await kbApi.delete(kbId.value);
    ui.toast("知识库已删除", "success");
    router.replace("/knowledge-bases");
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

async function removeDoc(doc: Document) {
  const ok = await ui.confirm({
    title: `删除文档「${doc.title}」?`,
    description: "其切片与向量索引将一并删除,不可恢复。",
    confirmText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await documentApi.delete(kbId.value, doc.id);
    ui.toast("文档已删除", "success");
    await refreshAll();
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

async function reindexDoc(doc: Document) {
  const ok = await ui.confirm({
    title: `重建「${doc.title}」的索引?`,
    description: "将按当前知识库参数重新解析并生成切片,作为新版本保存。",
    confirmText: "重建索引",
  });
  if (!ok) return;
  try {
    await documentApi.reindex(kbId.value, doc.id);
    ui.toast("已提交重建任务", "success");
    await refreshAll();
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

async function downloadDoc(doc: Document) {
  try {
    const blob = await documentApi.download(kbId.value, doc.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = doc.original_filename || doc.title;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

// ---- 展示辅助 ----
const DOC_ICONS: Record<string, unknown> = {
  pdf: FileText,
  docx: FileText,
  xlsx: FileSpreadsheet,
  xls: FileSpreadsheet,
  html: FileCode2,
  htm: FileCode2,
  md: FileCode2,
  markdown: FileCode2,
  txt: FileText,
};

function ext(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

function docIcon(doc: Document) {
  return DOC_ICONS[ext(doc.original_filename)] || FileIcon;
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("zh-CN");
}

const activeCount = computed(() => docs.value.filter((d) => d.status === "ready").length);
</script>

<template>
  <div class="page">
    <!-- 404 / 加载失败兜底 -->
    <template v-if="loadError">
      <PageHeader title="知识库不存在" :sub="loadError">
        <template #actions>
          <button class="btn btn-primary" type="button" @click="router.replace('/knowledge-bases')">
            返回知识库列表
          </button>
        </template>
      </PageHeader>
    </template>

    <template v-else>
      <PageHeader :title="kb?.name || '加载中…'" :sub="kb?.description || undefined">
        <template #back>
          <button
            class="btn btn-ghost btn-icon"
            type="button"
            title="返回"
            @click="router.push('/knowledge-bases')"
          >
            <ChevronLeft :size="18" />
          </button>
        </template>
        <template #actions>
          <button class="btn btn-ghost" type="button" @click="showEdit = true">编辑参数</button>
          <button class="btn btn-ghost btn-danger-text" type="button" @click="removeKb">删除</button>
          <button class="btn btn-accent" type="button" @click="showUpload = true">上传文档</button>
        </template>
      </PageHeader>

      <div class="stat-row">
        <div class="stat">
          <span class="stat-num">{{ docs.length }}</span>
          <span class="stat-label">文档总数</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ activeCount }}</span>
          <span class="stat-label">已就绪可检索</span>
        </div>
        <div class="stat" v-if="kb?.chunk_size">
          <span class="stat-num">{{ kb.chunk_size }}<small class="unit">字</small></span>
          <span class="stat-label">切片长度</span>
        </div>
        <div class="stat" v-if="kb?.chunk_overlap != null">
          <span class="stat-num">{{ kb.chunk_overlap }}<small class="unit">字</small></span>
          <span class="stat-label">切片重叠</span>
        </div>
      </div>

      <div v-if="loading" class="col doc-list">
        <div v-for="i in 3" :key="i" class="card doc-row">
          <div class="skeleton" style="height: 16px; width: 40%" />
          <div class="skeleton" style="height: 12px; width: 25%" />
        </div>
      </div>

      <EmptyState
        v-else-if="!docs.length"
        title="还没有文档"
        description="支持 PDF、Word、Excel、HTML、Markdown 与纯文本,单文件最大 50MB;相同内容的文件会自动去重为新版本。"
      >
        <button class="btn btn-accent" type="button" @click="showUpload = true">上传文档</button>
      </EmptyState>

      <div v-else class="col doc-list">
        <div v-for="doc in docs" :key="doc.id" class="card doc-row">
          <component :is="docIcon(doc)" :size="20" class="doc-icon" />
          <div class="doc-main">
            <div class="row" style="gap: var(--sp-2); align-items: center">
              <span class="doc-title">{{ doc.title }}</span>
              <StatusBadge :status="doc.status" kind="document" />
            </div>
            <div class="doc-meta">
              {{ fmtSize(doc.file_size) }} · v{{ doc.current_version_number }}
              <template v-if="doc.status === 'ready'"> · {{ doc.chunk_count }} 切片</template>
              · {{ fmtDate(doc.created_at) }}
            </div>
            <div v-if="doc.status === 'failed' && doc.error_message" class="doc-error">
              {{ doc.error_message }}
            </div>
          </div>
          <div class="doc-actions">
            <button class="btn btn-ghost btn-sm" type="button" @click="previewDoc = doc">预览</button>
            <button class="btn btn-ghost btn-sm" type="button" @click="downloadDoc(doc)">下载</button>
            <button class="btn btn-ghost btn-sm" type="button" @click="reindexDoc(doc)">重建索引</button>
            <button class="btn btn-ghost btn-sm btn-danger-text" type="button" @click="removeDoc(doc)">
              删除
            </button>
          </div>
        </div>
      </div>
    </template>

    <KbFormModal v-if="kb" :open="showEdit" :kb="kb" @close="showEdit = false" @saved="loadKb" />
    <UploadModal
      :open="showUpload"
      :kb-id="kbId"
      @close="showUpload = false"
      @uploaded="refreshAll"
    />
    <DocPreviewModal
      :open="!!previewDoc"
      :kb-id="kbId"
      :doc-id="previewDoc?.id || ''"
      :doc-title="previewDoc?.title || ''"
      @close="previewDoc = null"
    />
  </div>
</template>

<style scoped>
.page {
  padding: var(--sp-6);
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
}

.stat-row {
  display: flex;
  gap: var(--sp-8);
  margin-bottom: var(--sp-5);
  flex-wrap: wrap;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.stat-num .unit {
  font-size: var(--fs-xs);
  font-weight: 400;
  color: var(--text-3);
  margin-left: 3px;
}

.stat-label {
  font-size: var(--fs-xs);
  color: var(--text-3);
}

.doc-list {
  gap: var(--sp-3);
}

.doc-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
}

.doc-icon {
  color: var(--text-3);
  flex-shrink: 0;
}

.doc-main {
  flex: 1;
  min-width: 0;
}

.doc-title {
  font-weight: 500;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  font-size: var(--fs-xs);
  color: var(--text-3);
  margin-top: 2px;
}

.doc-error {
  margin-top: 2px;
  font-size: var(--fs-xs);
  color: var(--danger);
}

.doc-actions {
  display: flex;
  gap: var(--sp-1);
  flex-shrink: 0;
}

.btn-danger-text {
  color: var(--danger);
}

@media (max-width: 860px) {
  .doc-row {
    flex-wrap: wrap;
  }
  .doc-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
