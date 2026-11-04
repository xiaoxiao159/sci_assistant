import api from "./index";
import { streamSSE } from "./sse";

/** 真实引用(文档/版本/切片/页码/片段/分数,对齐后端 CitationItem)。 */
export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string;
  document_title: string | null;
  knowledge_base_id: string | null;
  version_number: number | null;
  page: number | null;
  snippet: string | null;
  score: number | null;
}

export interface ConversationSummary {
  id: string;
  project_id: string;
  title: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[] | null;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export interface AnswerResult {
  answer: string;
  conversation_id: string;
  citations: Citation[];
  insufficient_evidence: boolean;
}

export const conversationApi = {
  create: (projectId: string, data: { title?: string }) =>
    api
      .post<ConversationSummary>(`/projects/${projectId}/conversations`, data)
      .then((r) => r.data),
  listByProject: (projectId: string) =>
    api.get<ConversationSummary[]>(`/projects/${projectId}/conversations`).then((r) => r.data),
  get: (convId: string) =>
    api.get<{ id: string; project_id: string; title: string | null; messages: Message[] }>(
      `/conversations/${convId}`
    ).then((r) => r.data),
  messages: (convId: string) =>
    api.get<Message[]>(`/conversations/${convId}/messages`).then((r) => r.data),
  /** 非流式提交(备用路径)。 */
  send: (convId: string, data: { question: string; top_k?: number }) =>
    api.post<AnswerResult>(`/conversations/${convId}/messages`, data).then((r) => r.data),
  /** 流式提交(SSE:token -> citations -> done)。 */
  streamMessage: (
    convId: string,
    data: { question: string; top_k?: number },
    handlers: {
      onToken: (t: string) => void;
      onCitations: (d: { conversation_id: string; citations: Citation[] }) => void;
      onDone: () => void;
      onError: (m: string) => void;
    },
    signal?: AbortSignal
  ) => streamSSE(`/conversations/${convId}/messages/stream`, data, handlers, signal),
};
