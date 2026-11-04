import { defineStore } from "pinia";
import { ref } from "vue";
import { projectApi, type Project } from "@/api/project";
import { conversationApi, type ConversationSummary } from "@/api/conversation";

/**
 * 侧栏导航态:项目树(项目 → 会话)。
 * 项目与会话置顶直达;项目为用户直属,不再有工作空间分组。
 */
export const useNavStore = defineStore("nav", () => {
  const projects = ref<Project[]>([]);
  const conversationsByProject = ref<Record<string, ConversationSummary[]>>({});
  const expandedProjectIds = ref<Set<string>>(new Set());
  const loading = ref(false);
  const loaded = ref(false);

  /** 拉取全部项目(树需要全量;个人使用规模下可接受)。 */
  async function ensureProjects(force = false) {
    if (loaded.value && !force) return;
    loading.value = true;
    try {
      projects.value = await projectApi.list();
      loaded.value = true;
    } finally {
      loading.value = false;
    }
  }

  /** 展开项目时拉取其会话;失败以空列表兜底。 */
  async function ensureConversations(projectId: string) {
    try {
      const list = await conversationApi.listByProject(projectId);
      conversationsByProject.value = { ...conversationsByProject.value, [projectId]: list };
    } catch {
      conversationsByProject.value = { ...conversationsByProject.value, [projectId]: [] };
    }
  }

  /** 新会话产生后刷新对应项目的会话列表。 */
  async function refreshConversations(projectId: string) {
    await ensureConversations(projectId);
  }

  async function toggleExpandProject(projectId: string) {
    const next = new Set(expandedProjectIds.value);
    if (next.has(projectId)) {
      next.delete(projectId);
      expandedProjectIds.value = next;
    } else {
      next.add(projectId);
      expandedProjectIds.value = next;
      await ensureConversations(projectId);
    }
  }

  /** 展开到指定项目(+ 会话),用于路由激活时自动展开。 */
  async function reveal(projectId: string) {
    if (!expandedProjectIds.value.has(projectId)) {
      expandedProjectIds.value = new Set(expandedProjectIds.value).add(projectId);
      await ensureConversations(projectId);
    }
  }

  /** 增删改后调用:下次进入视图重新拉取。 */
  function invalidate() {
    projects.value = [];
    conversationsByProject.value = {};
    expandedProjectIds.value = new Set();
    loaded.value = false;
  }

  return {
    projects, conversationsByProject, expandedProjectIds, loading, loaded,
    ensureProjects, ensureConversations, refreshConversations,
    toggleExpandProject, reveal, invalidate,
  };
});
