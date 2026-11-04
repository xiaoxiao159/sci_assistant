import api from "./index";

export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface TaskEvent {
  id: string;
  status: string;
  detail: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  owner_id?: string;
  task_type: string;
  status: "pending" | "running" | "succeeded" | "failed";
  payload?: Record<string, unknown>;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at: string | null;
  events?: TaskEvent[];
}

export type TaskStatus = Task["status"];

export const taskApi = {
  list: (params: { status?: TaskStatus; offset?: number; limit?: number } = {}) =>
    api.get<Page<Task>>("/tasks", { params }).then((r) => r.data),
  get: (id: string) => api.get<Task>(`/tasks/${id}`).then((r) => r.data),
  retry: (id: string) => api.post<Task>(`/tasks/${id}/retry`).then((r) => r.data),
};
