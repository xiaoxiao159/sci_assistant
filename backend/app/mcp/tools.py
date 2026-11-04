"""MCP Tool handlers(规范 §9)。

每个 handler 只做:参数验证 → 认证授权 → 限流 → 调 RAG 内部接口/服务层 →
结果转换 → 安全错误映射。不复制检索/索引逻辑,不写 SQL,不暴露 ORM 对象。

错误约定:ToolError(message) 返回给客户端(is_error=true);消息只含
"code: 用户可读说明",不含堆栈/SQL/路径/密钥(内部细节进日志)。
"""
from contextlib import contextmanager

from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.logger import logger
from app.mcp import auth
from app.mcp.schemas import (
    CitationOut,
    DocumentContentOut,
    DocumentInfoOut,
    DocumentVersionOut,
    IndexTriggerOut,
    QueryOut,
    SearchOut,
)
from app.models import User
from app.rag.interfaces import rag_service
from app.rag.retrieval import retriever
from app.repositories import project_repo
from app.services import document_service, knowledge_base_service

# top_k 参数边界(防拉全库)
MAX_TOP_K = 20


# ─────────────────────── 公共骨架 ───────────────────────

@contextmanager
def _session():
    """独立 DB 会话(与 HTTP 请求生命周期无关,工具执行完即关)。"""
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_api_key(ctx: Context | None) -> str | None:
    """取本次调用的 API Key:http 走 X-API-Key 头;stdio 走 MCP_API_KEY 环境变量。"""
    headers = None
    if ctx is not None:
        try:
            headers = ctx.headers  # stdio / 无请求上下文时为 None 或抛 ValueError
        except Exception:  # noqa: BLE001
            headers = None
    if headers:
        # Starlette Headers 键统一小写
        return headers.get("x-api-key") or headers.get("X-API-Key")
    import os

    return os.environ.get("MCP_API_KEY") or None


def _authorized(db: Session, ctx: Context | None, tool: str, *, limit: int | None = None):
    """认证 + per-key 限流。返回 (user, api_key)。"""
    api_key = _current_api_key(ctx)
    user = auth.authenticate(db, api_key)
    auth.check_tool_rate_limit(api_key or "", tool, limit=limit)
    return user, api_key or ""


def _map_app_error(e: AppError) -> ToolError:
    """AppError -> ToolError(安全映射,只带 code + 用户可读消息)。"""
    code = {
        NotFoundError: "not_found",
        PermissionDeniedError: "forbidden",
        ConflictError: "conflict",
        ValidationError: "invalid_parameter",
    }.get(type(e), "error")
    return ToolError(f"{code}: {e.message}")


def _check_top_k(top_k: int) -> int:
    if not isinstance(top_k, int) or top_k < 1:
        raise ToolError("invalid_parameter: top_k 必须是 >= 1 的整数")
    return min(top_k, MAX_TOP_K)


def _get_owned_project(db: Session, owner_id: str, project_id: str):
    project = project_repo.get(db, project_id)
    if project is None or str(project.owner_id) != owner_id:
        raise NotFoundError("项目不存在或无权访问")
    return project


# ─────────────────────── 工具实现 ───────────────────────

def search_knowledge_base(kb_id: str, query: str, top_k: int = 5, ctx: Context = None) -> dict:
    """在指定知识库中语义检索,返回带引用的相关片段(只读,不调用 LLM)。

    Args:
        kb_id: 知识库 ID(必须属于 API Key 绑定的用户)
        query: 检索查询
        top_k: 返回片段数(1-20,默认 5)
    """
    top_k = _check_top_k(top_k)
    if not query or not query.strip():
        raise ToolError("invalid_parameter: query 不能为空")
    with _session() as db:
        try:
            user, _ = _authorized(db, ctx, "search")
            # 鉴权:KB 必须是当前用户的(不是则 not_found,不泄露存在性)
            knowledge_base_service.get(db, str(user.id), kb_id)
            result = retriever.retrieve(db, query.strip(), [kb_id], top_k=top_k)
            log_action(str(user.id), "mcp_search", f"kb={kb_id} q={query[:40]}")
            return SearchOut(
                query=query,
                total=result.total,
                citations=[CitationOut(**c.to_dict()) for c in result.citations],
            ).model_dump()
        except ToolError:
            raise
        except AppError as e:
            raise _map_app_error(e) from None
        except Exception:  # noqa: BLE001
            logger.exception("MCP search_knowledge_base 失败")
            raise ToolError("internal_error: 服务内部错误,请稍后重试") from None


def query_knowledge_base(project_id: str, question: str, top_k: int = 5, ctx: Context = None) -> dict:
    """在项目范围内检索并生成带真实引用的回答(只读;证据不足时明确说明,不伪造引用)。

    Args:
        project_id: 项目 ID(检索范围=该项目挂载且启用的知识库)
        question: 问题
        top_k: 检索片段数(1-20,默认 5)
    """
    top_k = _check_top_k(top_k)
    if not question or not question.strip():
        raise ToolError("invalid_parameter: question 不能为空")
    with _session() as db:
        try:
            user, _ = _authorized(
                db, ctx, "query", limit=settings.MCP_QUERY_RATE_LIMIT
            )
            _get_owned_project(db, str(user.id), project_id)
            answer = rag_service.query(db, project_id, question.strip(), top_k=top_k)
            log_action(str(user.id), "mcp_query", f"project={project_id} q={question[:40]}")
            return QueryOut(
                question=question,
                answer=answer.answer,
                insufficient_evidence=answer.insufficient_evidence,
                citations=[CitationOut(**c.to_dict()) for c in answer.citations],
            ).model_dump()
        except ToolError:
            raise
        except AppError as e:
            raise _map_app_error(e) from None
        except Exception:  # noqa: BLE001
            logger.exception("MCP query_knowledge_base 失败")
            raise ToolError("internal_error: 服务内部错误,请稍后重试") from None


def get_document_info(document_id: str, ctx: Context = None) -> dict:
    """获取授权文档的元数据与版本列表(只读)。"""
    with _session() as db:
        try:
            user, _ = _authorized(db, ctx, "get_document_info")
            doc = document_service.get_document(db, str(user.id), document_id)  # 经 KB 鉴权
            versions = document_service.list_versions(db, str(user.id), document_id)
            log_action(str(user.id), "mcp_get_document_info", f"doc={document_id}")
            return DocumentInfoOut(
                document_id=str(doc.id),
                title=doc.title,
                original_filename=doc.original_filename,
                mime_type=doc.mime_type or "",
                file_size=doc.file_size or 0,
                status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
                knowledge_base_id=str(doc.knowledge_base_id),
                current_version_number=doc.current_version_number,
                chunk_count=doc.chunk_count or 0,
                versions=[
                    DocumentVersionOut(
                        version_number=v.version_number,
                        status=v.status.value if hasattr(v.status, "value") else str(v.status),
                        parser_version=v.parser_version,
                        created_at=v.created_at.isoformat() if v.created_at else "",
                    )
                    for v in versions
                ],
            ).model_dump()
        except ToolError:
            raise
        except AppError as e:
            raise _map_app_error(e) from None
        except Exception:  # noqa: BLE001
            logger.exception("MCP get_document_info 失败")
            raise ToolError("internal_error: 服务内部错误,请稍后重试") from None


def get_document_content(document_id: str, max_chars: int | None = None, ctx: Context = None) -> dict:
    """获取授权文档当前版本的解析全文(输出长度受限,默认 8000 字符)。

    Args:
        document_id: 文档 ID
        max_chars: 期望返回的最大字符数(上限 MCP_MAX_CONTENT_CHARS)
    """
    limit = settings.MCP_MAX_CONTENT_CHARS
    if max_chars is not None:
        if not isinstance(max_chars, int) or max_chars < 1:
            raise ToolError("invalid_parameter: max_chars 必须是正整数")
        limit = min(max_chars, limit)
    with _session() as db:
        try:
            user, _ = _authorized(db, ctx, "get_document_content")
            content = document_service.get_content(db, str(user.id), document_id)
            text = content["text"] or ""
            log_action(str(user.id), "mcp_get_document_content", f"doc={document_id} chars={len(text)}")
            return DocumentContentOut(
                document_id=document_id,
                title=content.get("title") or "",
                version_number=content.get("version_number") or 0,
                total_chars=len(text),
                truncated=len(text) > limit,
                text=text[:limit],
            ).model_dump()
        except ToolError:
            raise
        except AppError as e:
            raise _map_app_error(e) from None
        except Exception:  # noqa: BLE001
            logger.exception("MCP get_document_content 失败")
            raise ToolError("internal_error: 服务内部错误,请稍后重试") from None


def index_document(document_id: str, ctx: Context = None) -> dict:
    """触发文档重新索引(写操作,默认关闭;需服务端设置 MCP_ENABLE_WRITE_TOOLS=true)。

    以当前版本内容创建新版本并入队索引任务;旧版本在新版本索引成功前保持可检索。
    """
    if not settings.MCP_ENABLE_WRITE_TOOLS:
        raise ToolError("forbidden: 写操作工具默认关闭(服务端设置 MCP_ENABLE_WRITE_TOOLS=true 后可用)")
    with _session() as db:
        try:
            user, _ = _authorized(db, ctx, "index_document")
            doc, version = document_service.reindex_document(db, str(user.id), document_id)
            log_action(str(user.id), "mcp_index_document", f"doc={document_id} -> v{version.version_number}")
            return IndexTriggerOut(
                document_id=str(doc.id),
                version_number=version.version_number,
                status="queued",
                message="索引任务已入队,可通过任务接口或 get_document_info 跟踪版本状态",
            ).model_dump()
        except ToolError:
            raise
        except AppError as e:
            raise _map_app_error(e) from None
        except Exception:  # noqa: BLE001
            logger.exception("MCP index_document 失败")
            raise ToolError("internal_error: 服务内部错误,请稍后重试") from None


# ─────────────────────── 注册 ───────────────────────

def register_tools(server) -> None:
    """把工具注册到 MCPServer(只读默认开;写操作默认关,handler 内再校验一次)。"""
    from mcp.types import ToolAnnotations

    server.tool(
        name="search_knowledge_base",
        description="在指定知识库中语义检索,返回带引用(文档/版本/页码/片段/分数)的相关片段。只读。",
        annotations=ToolAnnotations(read_only_hint=True),
    )(search_knowledge_base)
    server.tool(
        name="query_knowledge_base",
        description="在项目范围内检索已挂载知识库并生成带真实引用的回答;证据不足时明确说明,不伪造引用。只读。",
        annotations=ToolAnnotations(read_only_hint=True),
    )(query_knowledge_base)
    server.tool(
        name="get_document_info",
        description="获取授权文档的元数据(标题/类型/大小/状态)与版本列表。只读。",
        annotations=ToolAnnotations(read_only_hint=True),
    )(get_document_info)
    server.tool(
        name="get_document_content",
        description="获取授权文档当前版本的解析全文(输出长度受限,默认最多 8000 字符)。只读。",
        annotations=ToolAnnotations(read_only_hint=True),
    )(get_document_content)
    server.tool(
        name="index_document",
        description="触发文档重新索引(写操作,默认关闭,需服务端显式开启)。",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
    )(index_document)
