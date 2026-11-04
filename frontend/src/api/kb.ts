import api from "./index";

export interface Kb {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  doc_count: number;
  chunk_size: number | null;
  chunk_overlap: number | null;
  created_at: string;
}

export interface KbPayload {
  name?: string;
  description?: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

export const kbApi = {
  list: () => api.get<Kb[]>("/knowledge_bases").then((r) => r.data),
  get: (id: string) => api.get<Kb>(`/knowledge_bases/${id}`).then((r) => r.data),
  create: (data: KbPayload) => api.post<Kb>("/knowledge_bases", data).then((r) => r.data),
  update: (id: string, data: KbPayload) =>
    api.patch<Kb>(`/knowledge_bases/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/knowledge_bases/${id}`),
};
