<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/base/Modal.vue";
import { documentApi, type Chunk, type DocumentVersion } from "@/api/document";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";

/** 文档预览:源文件解析文本 / 切片 / 版本历史 三个 Tab(懒加载)。 */
const props = defineProps<{
  open: boolean;
  kbId: string;
  docId: string;
  docTitle: string;
}>();

const emit = defineEmits<{ close: [] }>();

const ui = useUiStore();
const tab = ref<"content" | "chunks" | "versions">("content");
const loading = ref(false);
const content = ref("");
const contentTruncated = ref(false);
const chunks = ref<Chunk[]>([]);
const versions = ref<DocumentVersion[]>([]);

const loadedTabs = ref(new Set<string>());

watch(
  () => [props.open, props.docId] as const,
  ([open]) => {
    if (!open) return;
    tab.value = "content";
    loadedTabs.value = new Set();
    content.value = "";
    chunks.value = [];
    versions.value = [];
    loadTab("content");
  }
);

watch(tab, (t) => {
  if (props.open) loadTab(t);
});

async function loadTab(t: "content" | "chunks" | "versions") {
  if (loadedTabs.value.has(t)) return;
  loadedTabs.value.add(t);
  loading.value = true;
  try {
    if (t === "content") {
      const res = await documentApi.getContent(props.kbId, props.docId);
      content.value = res.text;
      contentTruncated.value = res.text.length >= 50000;
    } else if (t === "chunks") {
      chunks.value = await documentApi.getChunks(props.kbId, props.docId);
    } else {
      versions.value = await documentApi.versions(props.kbId, props.docId);
    }
  } catch (e) {
    ui.toast(errMessage(e), "error");
  } finally {
    loading.value = false;
  }
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <Modal :open="open" :title="`预览 · ${docTitle}`" width="720px" @close="emit('close')">
    <div class="tabs">
      <button
        v-for="t in (['content', 'chunks', 'versions'] as const)"
        :key="t"
        class="tab"
        :class="{ active: tab === t }"
        type="button"
        @click="tab = t"
      >
        {{ t === "content" ? "解析文本" : t === "chunks" ? "切片" : "版本历史" }}
      </button>
    </div>

    <div class="tab-body">
      <div v-if="loading" class="col">
        <div class="skeleton" style="height: 14px" />
        <div class="skeleton" style="height: 14px; width: 80%" />
        <div class="skeleton" style="height: 14px; width: 65%" />
      </div>

      <template v-else-if="tab === 'content'">
        <pre class="pre-body">{{ content || "(无解析内容)" }}</pre>
        <p v-if="contentTruncated" class="text-xs text-3 mt-2">内容过长,仅显示前 50000 字符。</p>
      </template>

      <template v-else-if="tab === 'chunks'">
        <div v-if="!chunks.length" class="text-3 text-sm" style="padding: var(--sp-4)">暂无切片(文档索引完成后生成)。</div>
        <div v-else class="chunk-list">
          <div v-for="c in chunks" :key="c.id" class="chunk-card">
            <div class="row between">
              <span class="tag">切片 #{{ c.chunk_index + 1 }}</span>
              <span v-if="c.page" class="text-xs text-3">第 {{ c.page }} 页</span>
            </div>
            <p class="chunk-text">{{ c.text }}</p>
          </div>
        </div>
      </template>

      <template v-else>
        <div v-if="!versions.length" class="text-3 text-sm" style="padding: var(--sp-4)">暂无版本记录。</div>
        <div v-else class="ver-list">
          <div v-for="v in versions" :key="v.id" class="ver-row">
            <span class="ver-no">v{{ v.version_number }}</span>
            <span class="tag" :class="{ 'badge-success': v.status === 'indexed' }" style="padding: 1px 8px">{{ v.status }}</span>
            <span class="text-xs text-3">{{ fmtTime(v.created_at) }}</span>
            <span v-if="v.parser_version" class="text-xs text-3 mono">parser {{ v.parser_version }}</span>
          </div>
        </div>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: var(--sp-1);
  margin-bottom: var(--sp-4);
  border-bottom: 1px solid var(--border);
}

.tab {
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-2);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  margin-bottom: -1px;
}

.tab:hover { color: var(--text-1); }

.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.tab-body {
  min-height: 200px;
  max-height: 55vh;
  overflow-y: auto;
}

.pre-body {
  font-size: var(--fs-sm);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-1);
}

.chunk-list,
.ver-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.chunk-card {
  padding: var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.chunk-text {
  margin-top: var(--sp-2);
  font-size: var(--fs-sm);
  line-height: 1.7;
  color: var(--text-2);
  white-space: pre-wrap;
}

.ver-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) 0;
  border-bottom: 1px dashed var(--border);
  font-size: var(--fs-sm);
}

.ver-no {
  font-weight: 600;
  color: var(--text-1);
}
</style>
