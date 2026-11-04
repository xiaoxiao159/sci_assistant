import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

/** 记住上次的项目/会话位置,登录后直接回到那里。 */
const LAST_KEY = "sci_assistant_last_path";

function lastPosition(): string {
  const p = localStorage.getItem(LAST_KEY);
  return p && p.startsWith("/projects") ? p : "/projects";
}

/** 路由:全部懒加载;:id 一律参数化,刷新/深链安全。 */
const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/LoginView.vue"),
    meta: { layout: "auth", public: true },
  },
  { path: "/", redirect: () => lastPosition() },
  {
    path: "/projects",
    name: "projects",
    component: () => import("@/views/ProjectsView.vue"),
  },
  {
    path: "/projects/:projectId",
    name: "project-workbench",
    component: () => import("@/views/ProjectWorkbenchView.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/conversations/:conversationId",
    name: "conversation",
    component: () => import("@/views/ProjectWorkbenchView.vue"),
    props: true,
  },
  {
    path: "/knowledge-bases",
    name: "kbs",
    component: () => import("@/views/KnowledgeBasesView.vue"),
  },
  {
    path: "/knowledge-bases/:kbId",
    name: "kb-detail",
    component: () => import("@/views/KbDetailView.vue"),
    props: true,
  },
  {
    path: "/tasks",
    name: "tasks",
    component: () => import("@/views/TasksView.vue"),
  },
  { path: "/:pathMatch(.*)*", redirect: () => lastPosition() },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 记住项目/会话位置
router.afterEach((to) => {
  if (to.path.startsWith("/projects")) {
    localStorage.setItem(LAST_KEY, to.path);
  }
});

// 路由守卫:未登录跳登录页(带 redirect);已登录访问登录页 → 上次位置
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.token) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.token) {
    return { path: "/" };
  }
});

export default router;
