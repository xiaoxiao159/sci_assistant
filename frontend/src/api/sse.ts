import { API_BASE } from "./index";

export interface SSEEvents<T = unknown> {
  onToken?: (content: string) => void;
  onCitations?: (data: { conversation_id: string; citations: T[] }) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

/**
 * SSE 流式 POST(axios 不支持流式,用原生 fetch)。
 * 事件格式与后端 answer_stream 约定一致:data: {type: token|citations|done|error}。
 * 注意:fetch 不走 axios 拦截器,401 在此自行处理。
 */
export async function streamSSE<T = unknown>(
  url: string,
  body: unknown,
  handlers: SSEEvents<T>,
  signal?: AbortSignal
): Promise<void> {
  const token = localStorage.getItem("sci_assistant_token");
  const resp = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal,
  });
  if (resp.status === 401) {
    localStorage.removeItem("sci_assistant_token");
    localStorage.removeItem("sci_assistant_user");
    handlers.onError?.("登录已过期,请重新登录");
    window.location.href = "/login";
    return;
  }
  if (!resp.ok || !resp.body) {
    let msg = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      if (typeof data.detail === "string") msg = data.detail;
    } catch { /* 非 JSON 错误体 */ }
    handlers.onError?.(msg);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false; // 是否收到过终结事件(done/error)
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const evt = JSON.parse(line.slice(6));
        if (evt.type === "token") handlers.onToken?.(evt.content);
        else if (evt.type === "citations") handlers.onCitations?.(evt);
        else if (evt.type === "done") {
          finished = true;
          handlers.onDone?.();
        } else if (evt.type === "error") {
          finished = true;
          handlers.onError?.(evt.message || "服务内部错误");
        }
      } catch { /* 忽略解析失败 */ }
    }
  }
  // 流被服务端中途掐断(异常/断连):既无 done 也无 error,显式报错避免界面悬停
  if (!finished) handlers.onError?.("连接中断,回答未完成,请重试");
}
