# sci_assistant · 科研问答与写作系统 V1

> 多用户科研知识问答系统:知识库 → 文档摄入(解析/切片/嵌入)→ 检索增强问答(带引用)→ MCP 对外服务。

**核心能力(V1)**

- 用户注册登录(JWT);用户直属多个 Project,Project 挂载知识库
- 知识库(KB)是用户级可复用资产:一个 KB 可挂载到同用户的多个 Project
- 文档上传/版本管理/PDF 等解析/切片/bge-m3 嵌入/异步索引任务(可查状态、可重试)
- 项目级检索问答:跨"已挂载+启用+已索引"的 KB 检索,答案带真实引用(文档/版本/切片/页码/片段/得分)
- 会话与消息持久化,引用可回溯;空证据不编造,固定话术拒答
- MCP Server:检索/问答等能力以标准 MCP 工具对外(写入类工具默认关闭)
- 分层架构 + Alembic 迁移 + 测试套件

## 架构

```
接入层  Vue3 SPA(登录 / 知识库 / 项目工作台 / 对话)   MCP 客户端(Claude 等)
         │ HTTP(JWT)                                   │ MCP 协议(API Key)
网关层  FastAPI · 薄路由 + 统一错误体            app/mcp/(协议适配/鉴权/错误映射)
         │                                              │
业务层  services(用户/项目/KB/文档/会话/任务)
         │                                              │
RAG 层  app/rag/(独立模块,无 FastAPI/MCP 依赖)
        ingestion(解析/切片) · retrieval(混合检索+重排) · indexing(向量落库)
        RAGService = 内部 Python 接口 = MCP 工具 共用同一核心
         │
数据层  repositories(纯 CRUD)→ PostgreSQL(元数据+切片正文) · Milvus(向量) · Redis(缓存/会话) · MinIO(原件)
         │
异步层  Celery + Redis:文档索引任务(durable tasks 表 + 原子认领 + 恢复扫描 + 手动重试)
```

分层规则:API → Service → Repository → Database,依赖只朝下;`models/` 与 `schemas/` 是全局目录按域拆分;对外响应一律 Pydantic,不泄漏 ORM 对象。

## 数据模型(v8,11 张表)

```
users ─< projects >─ project_knowledge_bases ──> knowledge_bases
           │(同用户挂载:DB 复合外键强制)
           └─< conversations ─< messages(citations JSONB)
users ─< tasks ─< task_events
knowledge_bases ─< documents ─< document_versions ─< document_chunks
```

- 同用户挂载由 `UNIQUE(id, owner_id)` + 复合外键在**数据库层**强制,跨用户挂载不可能
- 被项目挂载的 KB 删除返回 **409**;文档版本切换原子化,旧版本在被替代前保持可见

## 目录结构

```
backend/
├── app/
│   ├── models/            v8 ORM 模型(11 表,全局目录)
│   ├── schemas/           Pydantic 请求/响应(按域拆分)
│   ├── api/               薄路由(auth/projects/kb/documents/conversations/tasks)
│   ├── services/          业务编排(auth/project/kb/document/conversation/task)
│   ├── repositories/      纯 CRUD
│   ├── rag/               RAG 独立模块:ingestion/retrieval/indexing/dto/citations/service
│   ├── mcp/               MCP 对外服务:server · tools · schemas · auth(API Key)
│   ├── providers/         llm(Bailian+SiliconFlow 故障切换)· embedding(bge-m3)· reranker
│   ├── workers/           Celery(索引任务 + beat 恢复扫描)
│   ├── database/          session · milvus(混合检索,partition_key=kb)
│   ├── storage/           minio · redis
│   ├── core/              config · security(JWT+bcrypt)· prompts · exceptions · logger
│   ├── evaluation/        RAG 评测(Recall@k + LLM-as-judge)
│   └── main.py            入口(全局异常处理器 + 僵死任务启动扫描)
├── alembic/               数据库迁移(env.py 读 app 配置;0001 v8 全量基线)
├── tests/                 测试套件(单元 + 集成,见下)
└── requirements.txt · .env.example
frontend/                  Vue3 + TS + Vite + Pinia SPA
deploy/docker-compose.yml  基础设施编排(PG/Milvus/Redis/MinIO/后端/Worker/前端)
```

## 快速开始

```bash
# 1. 基础设施(PG17 / Milvus / Redis / MinIO)
cd deploy && docker compose up -d postgres etcd minio milvus redis

# 2. 后端
cd backend
cp .env.example .env         # 填 LLM key 等
pip install -r requirements.txt
alembic upgrade head         # 建库建表(迁移可从空库执行)
uvicorn app.main:app --port 8001

# 3. Celery worker + beat(僵死任务恢复扫描,每 60s;Windows 不支持 -B,需分起两个进程)
celery -A app.workers.celery_app worker --pool=solo --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info

# 4. 前端
cd frontend && npm install && npm run dev

# 5. MCP Server(可选)
python -m app.mcp.server
```

## 环境变量

见 `backend/.env.example`(全部带注释;真实 key 只放本地 `.env`,不入库)。

主要分组:LLM(Bailian/SiliconFlow + 超时)、JWT、PostgreSQL、Redis、MinIO、Milvus、检索参数(TOP_K/候选数/RRF_K)、切片参数、嵌入/重排模型、解析器模式。

## API 概览(统一前缀 /api/v1)

| 域 | 端点 |
|---|---|
| 鉴权 | POST /auth/register · /auth/login · GET /auth/me |
| 项目 | POST/GET /projects · CRUD /projects/{id} · 挂载管理 /projects/{id}/knowledge-bases |
| 知识库 | CRUD /knowledge_bases(删除被挂载时 409) |
| 文档 | 上传/列表/详情/版本列表/重索引/切片/下载;扩展名白名单 + 50MB 上限 |
| 任务 | GET /tasks(分页+状态过滤)· GET /tasks/{id}(含事件流)· POST /tasks/{id}/retry |
| 会话 | POST /projects/{id}/conversations · GET 消息 · POST /conversations/{id}/messages(限流 20/min,SSE 流式) |

错误统一为 `{code, message, detail}`;分页统一 `{items, total, offset, limit}`。

## MCP 工具

| 工具 | 说明 | 默认 |
|---|---|---|
| search_knowledge_base | KB 内语义检索,返回带引用的片段 | 开 |
| query_knowledge_base | 项目级检索+生成,返回答案与真实引用 | 开 |
| get_document_info / get_document_content | 文档元信息 / 当前版本解析全文(限长) | 开 |
| index_document | 触发重建索引(写操作) | **关**(`MCP_ENABLE_WRITE_TOOLS=true` 开启) |

- **SDK**:`mcp==2.3.0`(v2,`MCPServer`);服务端与主后端同代码库、独立进程运行。
- **鉴权**:API Key 与用户绑定(`MCP_API_KEYS="key:email,key2:email2"`);每个 Key 只能访问
  绑定用户名下的资源;per-key 限流(Redis,query 更严);关键调用留审计日志。
- **错误映射**:业务异常转为 `ToolError`(`not_found/forbidden/conflict/invalid_parameter/rate_limited`),
  不泄露堆栈/SQL/路径/密钥。

### 启动与客户端连接

```bash
# .env 里配置 MCP_API_KEYS="sk-xxx:you@example.com"

# stdio(本地客户端;Key 经环境变量注入)
MCP_API_KEY=sk-xxx python -m app.mcp.server

# streamable-http(监听 127.0.0.1:8002/mcp;每次调用带 X-API-Key 头)
python -m app.mcp.server --transport http --port 8002
```

Claude Desktop / Claude Code 等 stdio 客户端配置示例:

```json
{
  "mcpServers": {
    "sci_assistant": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "<backend 绝对路径>",
      "env": { "MCP_API_KEY": "sk-xxx", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

双 transport 端到端冒烟(真实 MCP 客户端,自建独立测试库):

```bash
python test_data/mcp_smoke.py   # stdio + streamable-http 全链路验证
```

## 测试

```bash
cd backend
python -m pytest tests/ -v              # 全量:单元 + 集成(需本地 PostgreSQL)
python -m pytest tests/ -m "not integration" -v   # 仅单元测试(零外部依赖)
python test_data/mcp_smoke.py           # MCP 双 transport 端到端冒烟(独立测试库)
python tests/e2e_part_a.py              # 全栈冒烟(需 API + Celery worker 已启动)
```

- 集成测试自动重建测试库 `sci_assistant_test` 并以 `alembic upgrade head` 建表
  (每次运行即验证「迁移可从空库执行」);PG 不可达时自动跳过,不算失败。
- MinIO/Milvus/Redis/LLM 在集成测试中替换为内存实现,只验证真实 PG 上的业务行为。

覆盖(规范 §13):迁移从空库执行、跨用户读写全拒绝、跨用户挂载 DB 层兜底、
重复挂载幂等、挂载中 KB 删除 409、解除挂载后可删、任务原子领取/受控重试/僵死恢复、
索引幂等(重复索引不重复切片/向量)、内容去重、检索可见性(挂载+启用+当前版本)、
引用真实可回查、无证据不调 LLM 不伪造引用、会话/消息/引用持久化往返、
MCP 认证/越权/参数校验/限流/写工具默认关。
