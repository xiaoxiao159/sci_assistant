<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { useNavStore } from "@/stores/nav";
import type { Project } from "@/api/project";
import Dropdown from "@/components/base/Dropdown.vue";
import ProjectFormModal from "@/components/project/ProjectFormModal.vue";

const auth = useAuthStore();
const ui = useUiStore();
const nav = useNavStore();
const route = useRoute();
const router = useRouter();

const showNewProject = ref(false);

onMounted(() => {
  nav.ensureProjects();
});

// 进入项目/会话路由时,侧栏自动展开到对应位置
watch(
  () => route.params.projectId,
  (pid) => {
    if (typeof pid === "string") nav.reveal(pid);
  },
  { immediate: true }
);

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + "/");
}

function isProjectActive(id: string): boolean {
  return route.params.projectId === id;
}

function isConvActive(id: string): boolean {
  return route.params.conversationId === id;
}

/** 项目行点击 = 进入工作台并展开其会话;箭头点击 = 仅展开/收起。 */
async function onProjectRow(pid: string) {
  void router.push(`/projects/${pid}`);
  if (!nav.expandedProjectIds.has(pid)) await nav.toggleExpandProject(pid);
}

async function logout() {
  const ok = await ui.confirm({ title: "退出登录?", confirmText: "退出" });
  if (ok) {
    auth.logout();
    nav.invalidate();
    window.location.href = "/login";
  }
}

/** 侧栏新建项目后:刷新树并直接进入新项目工作台。 */
async function onProjectSaved(p: Project) {
  await nav.ensureProjects(true);
  void router.push(`/projects/${p.id}`);
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">研</div>
        <div class="brand-text">
          <div class="brand-name">科研问答助手</div>
          <div class="brand-sub">文献检索 · 引用溯源</div>
        </div>
      </div>

      <nav class="nav">
        <!-- 项目树置顶:项目 → 会话 -->
        <div class="nav-section">
          <div class="nav-section-head">
            <span class="nav-section-title">项目</span>
            <button
              class="btn btn-ghost btn-sm btn-icon"
              type="button"
              title="新建项目"
              @click="showNewProject = true"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5v14"/></svg>
            </button>
          </div>

          <div v-if="!nav.projects.length && nav.loading" class="tree-empty">加载中…</div>
          <div v-else-if="!nav.projects.length" class="tree-empty">
            还没有项目。点击 + 新建一个。
          </div>

          <div v-for="p in nav.projects" :key="p.id" class="proj-block">
            <div
              class="proj-item"
              :class="{ active: isProjectActive(p.id) }"
              :title="p.name"
              @click="onProjectRow(p.id)"
            >
              <svg
                width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
                class="chev"
                :style="{ transform: nav.expandedProjectIds.has(p.id) ? 'rotate(90deg)' : 'none' }"
                @click.stop="nav.toggleExpandProject(p.id)"
              ><path d="m9 18 6-6-6-6"/></svg>
              <span class="proj-name">{{ p.name }}</span>
            </div>

            <div v-if="nav.expandedProjectIds.has(p.id)" class="conv-list">
              <div
                v-if="!(nav.conversationsByProject[p.id] || []).length"
                class="tree-empty"
              >暂无会话</div>
              <div
                v-for="c in nav.conversationsByProject[p.id] || []"
                :key="c.id"
                class="conv-item"
                :class="{ active: isConvActive(c.id) }"
                :title="c.title || '未命名对话'"
                @click="$router.push(`/projects/${p.id}/conversations/${c.id}`)"
              >
                <span class="conv-name">{{ c.title || "未命名对话" }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="nav-sep" />

        <div
          class="nav-item"
          :class="{ active: isActive('/knowledge-bases') }"
          @click="$router.push('/knowledge-bases')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
          <span class="flex-1">知识库</span>
        </div>

        <div
          class="nav-item"
          :class="{ active: isActive('/tasks') }"
          @click="$router.push('/tasks')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="m9 14 2 2 4-4"/></svg>
          <span class="flex-1">任务中心</span>
        </div>
      </nav>

      <div class="sidebar-foot">
        <Dropdown align="left">
          <template #trigger>
            <div class="user-box">
              <div class="avatar">{{ (auth.user?.display_name || auth.user?.username || "?").slice(0, 1) }}</div>
              <div class="user-meta">
                <div class="user-name">{{ auth.user?.display_name || auth.user?.username }}</div>
                <div class="user-email">{{ auth.user?.email }}</div>
              </div>
            </div>
          </template>
          <template #menu>
            <button class="menu-item" type="button" @click="ui.toggleTheme()">
              <svg v-if="ui.theme === 'dark'" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
              <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
              {{ ui.theme === "dark" ? "切换浅色主题" : "切换深色主题" }}
            </button>
            <div class="menu-sep" />
            <button class="menu-item danger" type="button" @click="logout">退出登录</button>
          </template>
        </Dropdown>
      </div>
    </aside>

    <main class="main">
      <slot />
    </main>

    <ProjectFormModal
      :open="showNewProject"
      @close="showNewProject = false"
      @saved="onProjectSaved"
    />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100%;
}

.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-5) var(--sp-4);
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-on-brand);
  background: var(--brand);
  border-radius: var(--r-md);
  flex-shrink: 0;
}

.brand-name {
  font-size: var(--fs-lg);
  font-weight: 600;
  line-height: 1.3;
}

.brand-sub {
  font-size: var(--fs-xs);
  color: var(--text-3);
}

.nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2) var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.nav-section {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.nav-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-2) var(--sp-3) var(--sp-1);
}

.nav-section-title {
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--text-3);
}

.nav-sep {
  height: 1px;
  margin: var(--sp-2) var(--sp-2);
  background: var(--border);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-md);
  font-weight: 500;
  color: var(--text-2);
  border-radius: var(--r-md);
  cursor: pointer;
}

.nav-item:hover {
  background: var(--surface-2);
  color: var(--text-1);
}

.nav-item.active {
  background: var(--brand-soft);
  color: var(--brand);
}

:root[data-theme="dark"] .nav-item.active {
  color: var(--accent);
  background: var(--accent-soft);
}

/* ---- 项目树 ---- */
.chev {
  color: var(--text-3);
  transition: transform 0.15s ease;
  flex-shrink: 0;
}

.proj-block {
  display: flex;
  flex-direction: column;
}

.proj-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--text-2);
  border-radius: var(--r-sm);
  cursor: pointer;
}

.proj-item:hover {
  background: var(--surface-2);
  color: var(--text-1);
}

.proj-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 500;
}

.proj-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: var(--sp-1) 0 var(--sp-1) var(--sp-4);
  border-left: 1px dashed var(--border);
  margin-left: var(--sp-4);
}

.conv-item {
  padding: var(--sp-1) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--text-2);
  border-radius: var(--r-sm);
  cursor: pointer;
}

.conv-item:hover {
  background: var(--surface-2);
  color: var(--text-1);
}

.conv-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 500;
}

.conv-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-empty {
  padding: var(--sp-1) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--text-3);
  line-height: 1.6;
}

.sidebar-foot {
  padding: var(--sp-3);
  border-top: 1px solid var(--border);
}

.user-box {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
}

.user-box:hover {
  background: var(--surface-2);
}

.avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-weight: 600;
  color: var(--text-on-brand);
  background: var(--brand);
  border-radius: var(--r-full);
  flex-shrink: 0;
}

.user-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  line-height: 1.3;
}

.user-email {
  font-size: var(--fs-xs);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
}

.main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}
</style>
