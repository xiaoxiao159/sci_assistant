<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import KbFormModal from "@/components/kb/KbFormModal.vue";
import { kbApi, type Kb } from "@/api/kb";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 知识库列表:卡片网格,整卡点击进入详情。 */
const router = useRouter();
const ui = useUiStore();

const kbs = ref<Kb[]>([]);
const loading = ref(true);
const showForm = ref(false);
const editing = ref<Kb | null>(null);

async function load() {
  loading.value = true;
  try {
    kbs.value = await kbApi.list();
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function openCreate() {
  editing.value = null;
  showForm.value = true;
}

function openEdit(kb: Kb) {
  editing.value = kb;
  showForm.value = true;
}

async function removeKb(kb: Kb) {
  const ok = await ui.confirm({
    title: `删除知识库「${kb.name}」?`,
    description: "将同时删除其下所有文档、切片与向量索引,不可恢复。",
    confirmText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await kbApi.delete(kb.id);
    ui.toast("知识库已删除", "success");
    await load();
  } catch (e) {
    // 409:仍被项目挂载等,后端返回中文说明,直接透出
    ui.toast(errMessage(e), "error");
  }
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN");
}
</script>

<template>
  <div class="page">
    <PageHeader title="知识库" sub="上传文献资料,构建可检索、可溯源的知识来源">
      <template #actions>
        <button class="btn btn-primary" type="button" @click="openCreate">新建知识库</button>
      </template>
    </PageHeader>

    <div v-if="loading" class="grid-kb">
      <div v-for="i in 3" :key="i" class="card skeleton-card">
        <div class="skeleton" style="height: 18px; width: 55%" />
        <div class="skeleton" style="height: 13px; width: 80%" />
        <div class="skeleton" style="height: 13px; width: 40%" />
      </div>
    </div>

    <EmptyState
      v-else-if="!kbs.length"
      title="还没有知识库"
      description="新建一个知识库,上传 PDF / Word / Excel / Markdown / 文本文献,即可在项目问答中引用。"
    >
      <button class="btn btn-primary" type="button" @click="openCreate">新建知识库</button>
    </EmptyState>

    <div v-else class="grid-kb">
      <div
        v-for="kb in kbs"
        :key="kb.id"
        class="card card-hover kb-card"
        role="link"
        tabindex="0"
        @click="router.push(`/knowledge-bases/${kb.id}`)"
        @keydown.enter="router.push(`/knowledge-bases/${kb.id}`)"
      >
        <div class="row between">
          <h3 class="kb-name">{{ kb.name }}</h3>
          <span class="tag" :class="{ 'tag-archived': kb.status !== 'active' }">
            {{ kb.status === "active" ? "启用中" : "已归档" }}
          </span>
        </div>
        <p class="kb-desc">{{ kb.description || "暂无描述" }}</p>
        <div class="row between kb-meta">
          <span class="text-xs text-3">{{ kb.doc_count }} 篇文档 · 建于 {{ fmtDate(kb.created_at) }}</span>
          <span class="row actions" @click.stop>
            <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(kb)">编辑</button>
            <button class="btn btn-ghost btn-sm btn-danger-text" type="button" @click="removeKb(kb)">
              删除
            </button>
          </span>
        </div>
      </div>
    </div>

    <KbFormModal :open="showForm" :kb="editing" @close="showForm = false" @saved="load" />
  </div>
</template>

<style scoped>
.page {
  padding: var(--sp-6);
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.kb-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.kb-name {
  margin: 0;
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-desc {
  margin: var(--sp-2) 0 var(--sp-4);
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--text-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
}

.kb-meta {
  align-items: center;
}

.tag {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  background: var(--accent-soft);
  color: var(--accent);
}

.tag-archived {
  background: var(--surface-2);
  color: var(--text-3);
}

.btn-danger-text {
  color: var(--danger);
}
</style>
