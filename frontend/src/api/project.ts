import api from "./index";
import type { Kb } from "./kb";

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface MountedKb {
  knowledge_base_id: string;
  name: string;
  description: string | null;
  status: string;
  doc_count: number;
  mounted_at: string | null;
}

export const projectApi = {
  list: () => api.get<Project[]>("/projects").then((r) => r.data),
  get: (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data),
  create: (data: { name: string; description?: string }) =>
    api.post<Project>("/projects", data).then((r) => r.data),
  update: (id: string, data: { name?: string; description?: string }) =>
    api.patch<Project>(`/projects/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/projects/${id}`),
  // 挂载管理(检索范围 = 项目挂载且启用的 KB)
  listMountedKbs: (id: string) =>
    api.get<MountedKb[]>(`/projects/${id}/knowledge-bases`).then((r) => r.data),
  mountKb: (id: string, kbId: string) =>
    api.post(`/projects/${id}/knowledge-bases`, { knowledge_base_id: kbId }),
  unmountKb: (id: string, kbId: string) =>
    api.delete(`/projects/${id}/knowledge-bases/${kbId}`),
};

export type { Kb };
