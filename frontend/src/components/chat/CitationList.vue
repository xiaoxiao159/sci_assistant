<script setup lang="ts">
import { ref } from "vue";
import type { Citation } from "@/api/conversation";

/** 引用面板:每条 = 角标 + 文档标题 + 版本/页码 + 相关度 + 可展开片段。 */
const props = defineProps<{
  citations: Citation[];
  highlightIndex?: number | null;
}>();

const expanded = ref<Set<string>>(new Set());

function toggle(c: Citation) {
  const key = c.chunk_id;
  const next = new Set(expanded.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expanded.value = next;
}

function fmtScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(3);
}
</script>

<template>
  <div class="cites">
    <div class="cites-head">引用来源({{ citations.length }})</div>
    <div class="cites-list">
      <div
        v-for="c in citations"
        :key="c.chunk_id + c.index"
        class="cite-card"
        :class="{ highlighted: highlightIndex === c.index }"
      >
        <button class="cite-main" type="button" @click="toggle(c)">
          <span class="cite-no">{{ c.index }}</span>
          <span class="cite-title">{{ c.document_title || "未命名文档" }}</span>
          <span v-if="c.version_number" class="cite-ver">v{{ c.version_number }}</span>
          <span v-if="c.page" class="cite-ver">第 {{ c.page }} 页</span>
          <span class="cite-score" :title="`相关度 ${fmtScore(c.score)}`">
            <span class="score-bar" :style="{ width: Math.round((c.score ?? 0) * 100) + '%' }" />
            <span class="score-num">{{ fmtScore(c.score) }}</span>
          </span>
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            class="chevron" :style="{ transform: expanded.has(c.chunk_id) ? 'rotate(180deg)' : 'none' }"
          ><path d="m6 9 6 6 6-6"/></svg>
        </button>
        <div v-if="expanded.has(c.chunk_id)" class="cite-snippet">
          {{ c.snippet || "(无片段)" }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cites {
  margin-top: var(--sp-3);
  border-top: 1px dashed var(--border);
  padding-top: var(--sp-3);
}

.cites-head {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--text-3);
  margin-bottom: var(--sp-2);
}

.cites-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.cite-card {
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  overflow: hidden;
}

.cite-card.highlighted {
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.cite-main {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-1);
}

.cite-main:hover {
  background: var(--surface-2);
}

.cite-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: var(--r-full);
  flex-shrink: 0;
}

.cite-title {
  font-size: var(--fs-sm);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cite-ver {
  font-size: var(--fs-xs);
  color: var(--text-3);
  flex-shrink: 0;
}

.cite-score {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  margin-left: auto;
  flex-shrink: 0;
}

.score-bar {
  display: block;
  height: 4px;
  border-radius: var(--r-full);
  background: var(--accent);
  opacity: 0.65;
  min-width: 4px;
}

.score-num {
  font-size: var(--fs-xs);
  color: var(--text-3);
  font-family: var(--font-mono);
}

.chevron {
  color: var(--text-3);
  transition: transform 0.15s ease;
  flex-shrink: 0;
}

.cite-snippet {
  padding: var(--sp-2) var(--sp-3) var(--sp-3);
  font-size: var(--fs-sm);
  line-height: 1.7;
  color: var(--text-2);
  border-top: 1px dashed var(--border);
  background: var(--surface-2);
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}
</style>
