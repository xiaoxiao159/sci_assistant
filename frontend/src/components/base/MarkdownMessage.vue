<script setup lang="ts">
import { computed, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const props = withDefaults(
  defineProps<{
    content: string;
    streaming?: boolean;
  }>(),
  { streaming: false }
);

const emit = defineEmits<{ cite: [n: number] }>();

marked.setOptions({ breaks: true, gfm: true });

/** [n] -> 可点角标(负向前瞻避开 Markdown 链接语法 [text](url))。 */
function markCitations(src: string): string {
  return src.replace(/\[(\d{1,2})\](?!\()/g, '<sup class="cite" data-cite="$1">$1</sup>');
}

const html = ref("");

function render() {
  const raw = markCitations(props.content);
  const dirty = marked.parse(raw, { async: false }) as string;
  html.value = DOMPurify.sanitize(dirty, { ADD_ATTR: ["target", "data-cite"] });
}

// 流式期间节流重渲染(80ms),避免每个 token 都 parse 一遍
let timer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => props.content,
  () => {
    if (!props.streaming) {
      render();
      return;
    }
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      render();
    }, 80);
  },
  { immediate: true }
);

const streamingCursor = computed(() => props.streaming);

function onClick(e: MouseEvent) {
  const target = (e.target as HTMLElement).closest("sup.cite");
  if (target) {
    const n = Number(target.getAttribute("data-cite"));
    if (n) emit("cite", n);
  }
}
</script>

<template>
  <div class="md-body" @click="onClick">
    <span v-if="streamingCursor && !content" class="text-3">思考中…</span>
    <!-- eslint-disable-next-line vue/no-v-html —— 内容已经 DOMPurify 消毒 -->
    <span v-else v-html="html" />
    <span v-if="streamingCursor && content" class="cursor" />
  </div>
</template>

<style scoped>
.cursor {
  display: inline-block;
  width: 7px;
  height: 16px;
  margin-left: 2px;
  background: var(--accent);
  border-radius: 1px;
  animation: blink 1s steps(2) infinite;
  vertical-align: text-bottom;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
