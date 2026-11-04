import api from "./index";

export interface Document {
  id: string;
  knowledge_base_id: string;
  owner_id: string;
  title: string;
  original_filename: string;
  mime_type: string;
  file_size: number | null;
  status: "uploaded" | "processing" | "ready" | "failed";
  current_version_number: number;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface UploadResult {
  document_id: string;
  version_id: string;
  version_number: number;
  filename: string;
  status: string;
  is_dedup: boolean;
  task_id: string | null;
}

export interface Chunk {
  id: string;
  chunk_index: number;
  page: number | null;
  text: string;
  token_count: number | null;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  content_hash: string;
  file_size: number | null;
  status: string;
  parser_version: string | null;
  created_at: string;
}

// 与后端 app/api/documents.py 的白名单保持一致
export const ALLOWED_EXTENSIONS = ["pdf", "docx", "xlsx", "xls", "html", "htm", "md", "markdown", "txt"];
export const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

const _base = (kbId: string) => `/knowledge_bases/${kbId}/documents`;

export const documentApi = {
  list: (kbId: string) => api.get<Document[]>(_base(kbId)).then((r) => r.data),
  get: (kbId: string, docId: string) =>
    api.get<Document>(`${_base(kbId)}/${docId}`).then((r) => r.data),
  upload: (kbId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<UploadResult>(_base(kbId), form, { headers: { "Content-Type": "multipart/form-data" } })
      .then((r) => r.data);
  },
  versions: (kbId: string, docId: string) =>
    api.get<DocumentVersion[]>(`${_base(kbId)}/${docId}/versions`).then((r) => r.data),
  getChunks: (kbId: string, docId: string) =>
    api.get<Chunk[]>(`${_base(kbId)}/${docId}/chunks`).then((r) => r.data),
  getContent: (kbId: string, docId: string) =>
    api.get<{ title: string; version_number: number; text: string }>(
      `${_base(kbId)}/${docId}/content`
    ).then((r) => r.data),
  download: (kbId: string, docId: string) =>
    api.get(`${_base(kbId)}/${docId}/download`, { responseType: "blob" }).then((r) => r.data),
  reindex: (kbId: string, docId: string) =>
    api.post<{ document_id: string; version_number: number; task_id: string | null }>(
      `${_base(kbId)}/${docId}/reindex`
    ).then((r) => r.data),
  delete: (kbId: string, docId: string) => api.delete(`${_base(kbId)}/${docId}`),
};
