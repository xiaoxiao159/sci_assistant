<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  Plus,
  PanelRightClose,
  PanelRightOpen,
  ChevronLeft,
  BookOpen,
  Unlink,
} from "lucide-vue-next";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import MarkdownMessage from "@/components/base/MarkdownMessage.vue";
import CitationList from "@/components/chat/CitationList.vue";
import MountKbsModal from "@/components/project/MountKbsModal.vue";
import { projectApi, type Project, type MountedKb } from "@/api/project";
import { conversationApi, type Citation, type Message } from "@/api/conversation";
import { errMessage } from "@/api";
import { useUiStore } from "@/stores/ui";
import { useNavStore } from "@/stores/nav";

/**
 * 项目工作台:两栏 [对话主区][挂载知识库面板 280px 可折叠]。
 * 会话列表由侧栏承载(点击直达本页会话路由);流式问答走项目级 SSE 接口。
 */

interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  streaming?: boolean;
  error?: boolean;
  insufficient?: boolean;
}

const props = defineProps<{
  projectId: string;
  conversationId?: string;
}>();

const router = useRouter();
const ui = useUiStore();
const nav = useNavStore();

// ---- 项目与挂载 ----
const project = ref<Project | null>(null);
const mountedKbs = ref<MountedKb[]>([]);
const loadError = ref("");
const showMount = ref(false);
const panelOpen = ref(true);

async function loadProject() {
  try {
    project.value = await projectApi.get(props.projectId);
  } catch (e) {
    loadError.value = errMessage(e);
    ui.toast(loadError.value, "error");
  }
}

async function loadMounted() {
  try {
    mountedKbs.value = await projectApi.listMountedKbs(props.projectId);
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

async function unmount(kb: MountedKb) {
  const ok = await ui.confirm({
    title: `解除挂载「${kb.name}」?`,
    description: "解除后本项目的问答将不再检索该知识库。",
    confirmText: "解除",
  });
  if (!ok) return;
  try {
    await projectApi.unmountKb(props.projectId, kb.knowledge_base_id);
    ui.toast(`已解除「${kb.name}」`, "info");
    await loadMounted();
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

// ---- 会话(路由驱动:侧栏点会话 → /projects/:pid/conversations/:cid) ----
const msgs = ref<ChatMsg[]>([]);
const currentConvId = ref<string | null>(null);

async function openConversation(convId: string) {
  // 切换会话:先中止进行中的流,再载入历史
  abortCtl?.abort();
  streaming.value = false;
  currentConvId.value = convId;
  msgs.value = [];
  try {
    const list = await conversationApi.messages(convId);
    msgs.value = list
      .filter((m): m is Message & { role: "user" | "assistant" } =>
        m.role === "user" || m.role === "assistant"
      )
      .map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        citations: m.citations || [],
        insufficient: m.role === "assistant" && !(m.citations || []).length,
      }));
    scrollBottom();
  } catch (e) {
    ui.toast(errMessage(e), "error");
  }
}

/** "新对话":回到项目根路由(无会话参数)。 */
function newConversation() {
  if (streaming.value) abortCtl?.abort();
  void router.push(`/projects/${props.projectId}`);
}

// ---- 路由变化:项目切换全量重载;会话切换载入历史 ----
watch(
  () => [props.projectId, props.conversationId] as const,
  async ([pid, cid], old) => {
    const [oldPid] = old ?? [];
    if (pid !== oldPid) {
      abortCtl?.abort();
      streaming.value = false;
      loadError.value = "";
      project.value = null;
      mountedKbs.value = [];
      currentConvId.value = null;
      msgs.value = [];
      await loadProject();
      if (!loadError.value) await loadMounted();
    }
    if (cid && cid !== currentConvId.value) {
      await openConversation(cid);
    } else if (!cid && pid === oldPid && currentConvId.value) {
      // 项目未变、回到根路由 = 用户点了"新对话"
      abortCtl?.abort();
      streaming.value = false;
      currentConvId.value = null;
      msgs.value = [];
    }
  },
  { immediate: true }
);

// ---- 发送(流式) ----
const question = ref("");
const topK = ref(10);
const streaming = ref(false);
let abortCtl: AbortController | null = null;
let msgSeq = 0;

const canSend = computed(
  () => !streaming.value && question.value.trim().length > 0 && !loadError.value
);

async function send() {
  const q = question.value.trim();
  if (!q || streaming.value) return;
  question.value = "";
  autoGrow();

  msgs.value.push({ id: `u${++msgSeq}`, role: "user", content: q, citations: [] });
  const assistant: ChatMsg = {
    id: `a${++msgSeq}`,
    role: "assistant",
    content: "",
    citations: [],
    streaming: true,
  };
  msgs.value.push(assistant);
  streaming.value = true;
  scrollBottom();

  try {
    // 无会话则先创建(标题取问句前 40 字),并切到会话路由(可深链/刷新)
    if (!currentConvId.value) {
      const conv = await conversationApi.create(props.projectId, {
        title: q.slice(0, 40),
      });
      currentConvId.value = conv.id;
      void nav.refreshConversations(props.projectId);
      void router.replace(`/projects/${props.projectId}/conversations/${conv.id}`);
    }
    const convId = currentConvId.value!;

    abortCtl = new AbortController();
    await conversationApi.streamMessage(
      convId,
      { question: q, top_k: topK.value },
      {
        onToken: (t) => {
          assistant.content += t;
          scrollBottom();
        },
        onCitations: (d) => {
          assistant.citations = d.citations || [];
        },
        onDone: () => {
          // done 且无引用 → 证据不足(规范:证据不足不伪造,回答会说明)
          if (!assistant.citations.length) assistant.insufficient = true;
        },
        onError: (m) => {
          if (assistant && !assistant.content) {
            assistant.error = true;
            assistant.content = m;
          } else {
            ui.toast(m, "error");
          }
        },
      },
      abortCtl.signal
    );
  } catch (e) {
    if ((e as Error).name !== "AbortError") {
      if (!assistant.content) {
        assistant.error = true;
        assistant.content = errMessage(e);
      } else {
        ui.toast(errMessage(e), "error");
      }
    }
  } finally {
    assistant.streaming = false;
    streaming.value = false;
    abortCtl = null;
    scrollBottom();
  }
}

onBeforeUnmount(() => abortCtl?.abort());

// ---- 引用联动:[n] 角标 → 高亮对应引用卡并滚动到可见 ----
const highlightIdx = ref<number | null>(null);
let highlightTimer: ReturnType<typeof setTimeout> | null = null;

function onCite(n: number) {
  highlightIdx.value = n;
  if (highlightTimer) clearTimeout(highlightTimer);
  highlightTimer = setTimeout(() => (highlightIdx.value = null), 2500);
  nextTick(() => {
    document
      .querySelector(".cite-card.highlighted")
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}

// ---- 输入区:自动增高 + Enter 发送 ----
const inputEl = ref<HTMLTextAreaElement | null>(null);

function autoGrow() {
  const el = inputEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
}

// ---- 滚动 ----
const scrollEl = ref<HTMLElement | null>(null);

function scrollBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
  });
}

// 侧栏展开定位由 AppLayout 的路由 watcher 负责(nav.reveal)
</script>

<template>
  <div class="page">
    <template v-if="loadError">
      <PageHeader title="项目不存在" :sub="loadError">
        <template #actions>
          <button class="btn btn-primary" type="button" @click="router.replace('/projects')">
            返回项目列表
          </button>
        </template>
      </PageHeader>
    </template>

    <template v-else>
      <PageHeader :title="project?.name || '加载中…'">
        <template #back>
          <button
            class="btn btn-ghost btn-icon"
            type="button"
            title="返回项目列表"
            @click="router.push('/projects')"
          >
            <ChevronLeft :size="18" />
          </button>
        </template>
        <template #actions>
          <button class="btn btn-ghost" type="button" @click="newConversation">
            <Plus :size="15" style="margin-right: 4px" /> 新对话
          </button>
          <button
            class="btn btn-ghost btn-icon"
            type="button"
            :title="panelOpen ? '收起知识库面板' : '展开知识库面板'"
            @click="panelOpen = !panelOpen"
          >
            <PanelRightClose v-if="panelOpen" :size="18" />
            <PanelRightOpen v-else :size="18" />
          </button>
        </template>
      </PageHeader>

      <div class="bench" :class="{ 'panel-closed': !panelOpen }">
        <!-- 对话主区 -->
        <section class="chat">
          <div ref="scrollEl" class="chat-scroll">
            <EmptyState
              v-if="!msgs.length"
              title="向你的文献提问"
              :description="mountedKbs.length
                ? '回答基于本项目挂载的知识库生成,并附可溯源的引用。'
                : '先在右侧挂载知识库,再开始提问。'"
            />
            <template v-for="m in msgs" :key="m.id">
              <!-- 用户气泡 -->
              <div v-if="m.role === 'user'" class="bubble-row user">
                <div class="bubble user-bubble">{{ m.content }}</div>
              </div>
              <!-- 助手回答 -->
              <div v-else class="bubble-row">
                <div class="bubble assistant-bubble" :class="{ 'has-error': m.error }">
                  <MarkdownMessage :content="m.content" :streaming="!!m.streaming" @cite="onCite" />
                  <div v-if="m.insufficient && !m.streaming" class="insufficient">
                    本次回答未找到足够的文献证据,内容仅供参考;可尝试换一种问法或扩大检索范围。
                  </div>
                  <CitationList v-if="m.citations.length" :citations="m.citations" :highlight-index="highlightIdx" />
                </div>
              </div>
            </template>
          </div>

          <!-- 输入区 -->
          <div class="composer">
            <div v-if="!mountedKbs.length" class="kb-warn">
              本项目尚未挂载知识库,回答将没有文献依据。
              <button class="btn btn-accent btn-sm" type="button" @click="showMount = true">去挂载</button>
            </div>
            <div class="composer-row">
              <textarea
                ref="inputEl"
                v-model="question"
                class="textarea composer-input"
                rows="1"
                placeholder="基于已挂载的文献提问…(Enter 发送,Shift+Enter 换行)"
                :disabled="streaming || !!loadError"
                @keydown="onKeydown"
                @input="autoGrow"
              />
              <div class="composer-side">
                <select v-model="topK" class="select" title="检索引用条数">
                  <option :value="5">引用 5</option>
                  <option :value="10">引用 10</option>
                  <option :value="20">引用 20</option>
                </select>
                <button class="btn btn-primary" type="button" :disabled="!canSend" @click="send">
                  {{ streaming ? "回答中…" : "发送" }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 右:挂载知识库面板 -->
        <aside v-if="panelOpen" class="panel">
          <div class="panel-head">
            <BookOpen :size="15" />
            <span>知识库</span>
            <button class="btn btn-ghost btn-sm" type="button" @click="showMount = true">管理</button>
          </div>
          <div class="panel-scroll">
            <div v-if="!mountedKbs.length" class="text-xs text-3 panel-empty">
              未挂载任何知识库。挂载后,本项目问答将检索这些知识库中的文献。
            </div>
            <div v-for="kb in mountedKbs" :key="kb.knowledge_base_id" class="panel-kb">
              <div class="panel-kb-main">
                <span class="panel-kb-name" :title="kb.name">{{ kb.name }}</span>
                <span class="text-xs text-3">{{ kb.doc_count }} 篇</span>
              </div>
              <button
                class="btn btn-ghost btn-sm btn-icon"
                type="button"
                title="解除挂载"
                @click="unmount(kb)"
              >
                <Unlink :size="14" />
              </button>
            </div>
          </div>
          <div class="panel-foot">
            <span class="text-xs text-3">
              检索范围 = 已挂载且启用的知识库
            </span>
          </div>
        </aside>
      </div>

      <MountKbsModal
        :open="showMount"
        :project-id="projectId"
        @close="showMount = false"
        @changed="loadMounted"
      />
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--sp-4) var(--sp-6) var(--sp-5);
}

.page :deep(.page-head) {
  margin-bottom: var(--sp-4);
}

/* 两栏工作台:对话 + 挂载库 */
.bench {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: var(--sp-4);
}

.bench.panel-closed {
  grid-template-columns: 1fr;
}

/* 对话主区 */
.chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.bubble-row {
  display: flex;
}

.bubble-row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 82%;
  border-radius: var(--r-lg);
  padding: var(--sp-3) var(--sp-4);
  font-size: var(--fs-sm);
  line-height: 1.7;
}

.user-bubble {
  background: var(--brand);
  color: var(--bg);
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-bubble {
  background: var(--surface-2);
  border: 1px solid var(--border);
  min-width: 200px;
}

.assistant-bubble.has-error {
  border-color: var(--danger);
  color: var(--danger);
}

.insufficient {
  margin-top: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  background: var(--warning-soft);
  color: var(--warning);
  font-size: var(--fs-xs);
  line-height: 1.6;
}

/* 输入区 */
.composer {
  border-top: 1px solid var(--border);
  padding: var(--sp-3) var(--sp-4);
}

.kb-warn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  background: var(--warning-soft);
  color: var(--warning);
  font-size: var(--fs-xs);
}

.composer-row {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-end;
}

.composer-input {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 160px;
  line-height: 1.6;
}

.composer-side {
  display: flex;
  gap: var(--sp-2);
  align-items: center;
  flex-shrink: 0;
}

.composer-side .select {
  width: auto;
}

/* 右栏:挂载面板 */
.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--border);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-1);
}

.panel-head .btn {
  margin-left: auto;
}

.panel-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.panel-empty {
  padding: var(--sp-2);
  line-height: 1.6;
}

.panel-kb {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.panel-kb-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.panel-kb-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-foot {
  padding: var(--sp-2) var(--sp-4);
  border-top: 1px solid var(--border);
}

@media (max-width: 980px) {
  .bench,
  .bench.panel-closed {
    grid-template-columns: 1fr;
  }
  .panel { display: none; }
}
</style>
