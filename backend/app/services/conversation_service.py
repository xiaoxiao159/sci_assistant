"""会话与消息业务(v8):挂 Project,走 RAGService.query,引用持久化。

流程:鉴权 -> 会话 -> 落用户消息 -> 历史改写 -> RAG 检索+生成 -> 落助手消息(带引用)。
"""
import json

from sqlalchemy.orm import Session

from app.core import prompts
from app.core.audit import log_action
from app.core.exceptions import NotFoundError
from app.core.logger import logger
from app.models import MessageRole
from app.rag.interfaces import rag_service
from app.repositories import conversation_repo, message_repo, project_repo
from app.storage import redis_client


# ─────────────────────── 会话管理 ───────────────────────

def _get_owned_project(db: Session, owner_id: str, project_id: str):
    project = project_repo.get(db, project_id)
    if project is None or str(project.owner_id) != owner_id:
        raise NotFoundError("项目不存在或无权访问")
    return project


def create_conversation(db: Session, owner_id: str, project_id: str, title: str | None = None):
    _get_owned_project(db, owner_id, project_id)
    conv = conversation_repo.create(db, project_id=project_id, owner_id=owner_id, title=title)
    db.commit()
    return conv


def list_conversations(db: Session, owner_id: str, project_id: str):
    _get_owned_project(db, owner_id, project_id)
    return conversation_repo.list_by_project(db, project_id)


def get_conversation(db: Session, owner_id: str, project_id: str, conv_id: str):
    _get_owned_project(db, owner_id, project_id)
    conv = conversation_repo.get_with_messages(db, conv_id)
    if conv is None or str(conv.project_id) != project_id:
        raise NotFoundError("会话不存在或不属于该项目")
    return conv


def get_conversation_messages(db: Session, owner_id: str, conv_id: str, limit: int = 50):
    """消息列表:会话按 owner 鉴权(消息按时间正序)。"""
    conv = conversation_repo.get(db, conv_id)
    if conv is None or str(conv.owner_id) != owner_id:
        raise NotFoundError("会话不存在或无权访问")
    return message_repo.list_by_conversation(db, conv_id, limit=limit)


# ─────────────────────── 问答 ───────────────────────

def answer(db: Session, owner_id: str, project_id: str, question: str, *,
           conversation_id: str | None = None, top_k: int | None = None) -> dict:
    """项目内问答:检索 -> 生成 -> 双层记忆落库。

    返回 {answer, conversation_id, citations, insufficient_evidence}。
    """
    top_k = top_k or 5
    # ① 鉴权
    _get_owned_project(db, owner_id, project_id)
    system_prompt = prompts.DEFAULT_SYSTEM_PROMPT

    # ② 取/建会话
    conv = _get_or_create_conversation(db, owner_id, project_id, conversation_id, question)

    # ③ 落用户消息(PG 持久 + Redis 快层)
    message_repo.create(db, conversation_id=str(conv.id), role=MessageRole.user, content=question)
    db.commit()
    redis_client.append_message(str(conv.id), "user", question)

    # ④ 结果缓存(精确匹配,命中跳过检索+生成,省 LLM 成本)
    cached = redis_client.get_chat_cache(project_id, question)
    if cached:
        logger.info("命中 chat 缓存,跳过检索+生成")
        message_repo.create(
            db, conversation_id=str(conv.id), role=MessageRole.assistant,
            content=cached["answer"], citations=cached["sources"],
        )
        db.commit()
        redis_client.append_message(str(conv.id), "assistant", cached["answer"])
        return {
            "answer": cached["answer"], "conversation_id": str(conv.id),
            "citations": cached["sources"], "insufficient_evidence": False,
        }

    # ⑤ 历史上下文(Redis)+ 多轮改写
    history = redis_client.get_history(str(conv.id))
    standalone = _rewrite_query(question, history) if len(history) > 1 else question

    # ⑥ RAG:检索 + 生成(带引用;证据不足时 rag 明确说明,不伪造)
    rag_answer = rag_service.query(db, project_id, standalone, top_k=top_k)

    # ⑦ 落助手消息(带 citations)+ Redis
    citations_json = [c.to_dict() for c in rag_answer.citations]
    message_repo.create(
        db,
        conversation_id=str(conv.id),
        role=MessageRole.assistant,
        content=rag_answer.answer,
        citations=citations_json,
        meta={"provider": rag_answer.provider, "insufficient_evidence": rag_answer.insufficient_evidence},
    )
    db.commit()
    redis_client.append_message(str(conv.id), "assistant", rag_answer.answer)
    redis_client.set_chat_cache(project_id, question, rag_answer.answer, str(conv.id), citations_json)

    logger.info(f"RAG 回答完成(provider={rag_answer.provider}, citations={len(citations_json)})")
    log_action(owner_id, "chat", f"project={project_id} q={question[:40]}")
    return {
        "answer": rag_answer.answer,
        "conversation_id": str(conv.id),
        "citations": citations_json,
        "insufficient_evidence": rag_answer.insufficient_evidence,
    }


def answer_stream(db: Session, owner_id: str, project_id: str, question: str, *,
                  conversation_id: str | None = None, top_k: int | None = None):
    """流式问答(SSE):pre-step(同 answer ①-⑤)-> 流式生成 -> 落库。

    yield SSE 事件字符串:data: {type: token/citations/done}\n\n
    注意:流式路径不做结果缓存,直接走检索。
    """
    def sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    from app.providers import llm
    from app.rag import context_builder, citations as citations_mod
    from app.rag.retrieval import retriever

    top_k = top_k or 5
    try:
        _get_owned_project(db, owner_id, project_id)
        conv = _get_or_create_conversation(db, owner_id, project_id, conversation_id, question)
        message_repo.create(db, conversation_id=str(conv.id), role=MessageRole.user, content=question)
        db.commit()
        redis_client.append_message(str(conv.id), "user", question)
        history = redis_client.get_history(str(conv.id))
        standalone = _rewrite_query(question, history) if len(history) > 1 else question
        kb_ids = project_repo.get_active_mounted_kb_ids(db, project_id)
        chunks = retriever.retrieve_chunks(db, standalone, kb_ids, top_k=top_k)
        context_block = context_builder.build_context_block(chunks)
        user_prompt = context_builder.build_user_prompt(context_block, question)
        history = _compress_history(str(conv.id), history)
        msgs = [llm.ChatMessage(role="system", content=prompts.DEFAULT_SYSTEM_PROMPT)]
        for m in history:
            msgs.append(llm.ChatMessage(role=m["role"], content=m["content"]))
        msgs.append(llm.ChatMessage(role="user", content=user_prompt))
    except Exception as e:  # noqa: BLE001
        yield sse({"type": "error", "message": str(e)})
        return

    if not chunks:
        # 证据不足:明确说明,不伪造引用
        from app.rag.service import INSUFFICIENT_EVIDENCE_ANSWER

        no_evidence = INSUFFICIENT_EVIDENCE_ANSWER
        message_repo.create(
            db, conversation_id=str(conv.id), role=MessageRole.assistant,
            content=no_evidence, citations=[], meta={"insufficient_evidence": True},
        )
        db.commit()
        redis_client.append_message(str(conv.id), "assistant", no_evidence)
        yield sse({"type": "token", "content": no_evidence})
        yield sse({"type": "citations", "conversation_id": str(conv.id), "citations": []})
        yield sse({"type": "done"})
        return

    # 流式生成(逐 token yield);生成失败发 error 事件,避免前端挂在等待态
    parts: list[str] = []
    try:
        for token in llm.chat_stream(msgs, temperature=0.2):
            parts.append(token)
            yield sse({"type": "token", "content": token})
    except Exception as e:  # noqa: BLE001
        logger.error(f"流式生成失败(conversation={conv.id}): {e}")
        yield sse({"type": "error", "message": f"回答生成失败:{e}"})
        return

    answer_text = "".join(parts)
    citations_json = [c.to_dict() for c in citations_mod.build_citations(chunks)]
    message_repo.create(
        db, conversation_id=str(conv.id), role=MessageRole.assistant,
        content=answer_text, citations=citations_json,
    )
    db.commit()
    redis_client.append_message(str(conv.id), "assistant", answer_text)
    logger.info(f"RAG 流式回答完成(citations={len(citations_json)})")

    yield sse({"type": "citations", "conversation_id": str(conv.id), "citations": citations_json})
    yield sse({"type": "done"})


# ─────────────────────── 内部 ───────────────────────

def _get_or_create_conversation(
    db: Session, owner_id: str, project_id: str, conversation_id: str | None, question: str
):
    if conversation_id:
        conv = conversation_repo.get(db, conversation_id)
        if conv is None or str(conv.project_id) != project_id:
            raise NotFoundError("会话不存在或不属于该项目")
        return conv
    return conversation_repo.create(
        db, project_id=project_id, owner_id=owner_id, title=(question or "")[:40]
    )


def _rewrite_query(question: str, history: list[dict]) -> str:
    """多轮改写:把追问变成独立查询。失败则退回原问题。"""
    from app.providers import llm

    history_text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in history[-4:])
    prompt = [
        llm.ChatMessage(role="system", content=prompts.REWRITE_SYSTEM_PROMPT),
        llm.ChatMessage(role="user", content=f"对话历史:\n{history_text}\n\n追问:{question}\n\n独立查询:"),
    ]
    try:
        rewritten, _ = llm.chat(prompt, temperature=0.0, max_tokens=128)
        return rewritten.strip() or question
    except Exception as e:  # noqa: BLE001
        logger.warning(f"查询改写失败,用原问题: {e}")
        return question


def _compress_history(conv_id: str, history: list[dict]) -> list[dict]:
    """长对话:老历史压成摘要 + 最近 6 条原文。"""
    from app.providers import llm

    if len(history) <= 10:
        return history[-6:]
    summary = redis_client.get_summary(conv_id)
    if not summary:
        summary = _summarize_history(history[:-6])
        if summary:
            redis_client.set_summary(conv_id, summary)
    if summary:
        return [{"role": "system", "content": f"[之前对话摘要] {summary}"}] + history[-6:]
    return history[-6:]


def _summarize_history(old_messages: list[dict]) -> str:
    from app.providers import llm

    text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in old_messages)
    prompt = [
        llm.ChatMessage(role="system", content="把以下对话历史压缩成简洁摘要(保留关键信息/结论/上下文),不超过 200 字。"),
        llm.ChatMessage(role="user", content=text),
    ]
    try:
        summary, _ = llm.chat(prompt, temperature=0.0, max_tokens=256)
        return summary.strip()
    except Exception:
        return ""
