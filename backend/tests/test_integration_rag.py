"""集成测试(真实 PG):索引幂等、检索可见性、引用真实、无证据不伪造(规范 §13)。

外部依赖(MinIO/Embedding/Milvus/Reranker)替换为内存实现;验证的是
真实 PG 上的业务行为与约束:chunks 唯一键、版本可见切换、引用映射。
"""
import pytest

from app.models import DocumentChunk, DocumentStatus, VersionStatus
from app.rag.interfaces import rag_service
from app.repositories import chunk_repo, document_repo, project_repo
from app.services import conversation_service, document_service, knowledge_base_service, project_service

pytestmark = pytest.mark.integration

SAMPLE_MD = (
    "# 深度学习方法综述\n\n"
    "Transformer 架构通过自注意力机制建模长距离依赖,是当前大语言模型的基础。\n\n"
    "检索增强生成(RAG)把外部知识库与大模型结合,能有效缓解幻觉问题。\n\n"
    "对比学习通过拉近正样本、推远负样本学习表示,广泛用于向量检索。\n\n"
    "微调技术包括全参数微调、LoRA 低秩适配与提示工程等不同成本档位。\n"
)


@pytest.fixture
def indexed_doc(db, make_user, make_project, make_kb, fake_minio, fake_milvus,
                fake_embedding, fake_reranker, no_enqueue):
    """完整链路:A 用户 -> KB -> 上传 md -> 直接执行索引任务 -> ready。"""
    user = make_user("rag-owner@t.cn")
    project = make_project(str(user.id))
    kb = make_kb(str(user.id), "rag-kb")

    doc, version, dedup, task = document_service.upload_document(
        db, str(user.id), str(kb.id), "综述.md", SAMPLE_MD.encode("utf-8"), "text/markdown",
    )
    assert dedup is False and task is not None
    rag_service.index_document(db, str(doc.id), str(version.id))
    db.commit()
    return {
        "user": user, "project": project, "kb": kb,
        "doc": doc, "version": version, "task": task,
    }


# ─────────────────────── 索引:状态与产物 ───────────────────────

def test_index_marks_ready_and_creates_chunks(indexed_doc, db):
    doc = document_repo.get(db, str(indexed_doc["doc"].id))
    assert doc.status == DocumentStatus.ready
    assert doc.current_version_number == 1
    version = document_repo.get_current_version(db, doc)
    assert version.status == VersionStatus.indexed
    assert version.parser_version  # 记录了管线版本
    chunks = chunk_repo.get_by_version(db, str(version.id))
    assert len(chunks) >= 1
    assert all(c.text for c in chunks)


def test_reindex_idempotent_no_duplicate_chunks(indexed_doc, db, fake_milvus):
    """重复执行同版本索引:先清理旧产物再重建,chunk 数不翻倍(幂等)。"""
    doc = document_repo.get(db, str(indexed_doc["doc"].id))
    version = document_repo.get_current_version(db, doc)
    before = len(chunk_repo.get_by_version(db, str(version.id)))

    rag_service.index_document(db, str(doc.id), str(version.id))  # 直接重跑
    db.commit()

    after = len(chunk_repo.get_by_version(db, str(version.id)))
    assert after == before
    assert len(fake_milvus.rows) == after  # 向量库也不重复


def test_upload_dedup_same_content(indexed_doc, db, fake_minio, no_enqueue):
    """同名同内容再上传:去重,不建新版本、不建新任务。"""
    doc, version, dedup, task = document_service.upload_document(
        db, str(indexed_doc["user"].id), str(indexed_doc["kb"].id),
        "综述.md", SAMPLE_MD.encode("utf-8"), "text/markdown",
    )
    assert dedup is True
    assert task is None
    assert str(doc.id) == str(indexed_doc["doc"].id)
    assert version.version_number == 1


# ─────────────────────── 检索:可见性与引用 ───────────────────────

def test_retrieve_returns_real_citations(indexed_doc, db, fake_milvus):
    project = indexed_doc["project"]
    project_service.mount_kb(db, str(indexed_doc["user"].id), str(project.id), str(indexed_doc["kb"].id))

    result = rag_service.retrieve(db, str(project.id), "什么是检索增强生成")
    assert result.total >= 1
    for c in result.citations:
        # 引用必须指向真实存在的 chunk / 文档 / 版本
        assert c.document_id == str(indexed_doc["doc"].id)
        assert c.knowledge_base_id == str(indexed_doc["kb"].id)
        assert c.version_number == 1
        assert c.document_title == "综述.md"
        assert c.snippet  # 有片段
        assert db.get(DocumentChunk, c.chunk_id) is not None  # chunk 真实存在


def test_retrieve_scoped_to_mounted_active_kbs(indexed_doc, db, make_kb, fake_milvus):
    """未挂载 / archived 的 KB 不参与检索。"""
    user, project = indexed_doc["user"], indexed_doc["project"]

    # ① 未挂载:检索不到
    assert rag_service.retrieve(db, str(project.id), "检索增强生成").total == 0

    # ② 挂载后:能检索到
    project_service.mount_kb(db, str(user.id), str(project.id), str(indexed_doc["kb"].id))
    assert rag_service.retrieve(db, str(project.id), "检索增强生成").total >= 1

    # ③ KB archived:不再参与
    from app.schemas.knowledge_base import KbUpdate
    knowledge_base_service.update(db, str(user.id), str(indexed_doc["kb"].id), KbUpdate(status="archived"))
    assert rag_service.retrieve(db, str(project.id), "检索增强生成").total == 0


def test_query_no_evidence_no_fake_citations(indexed_doc, db, monkeypatch, fake_milvus):
    """无证据:不调 LLM、固定话术、引用为空(不伪造)。"""
    from app.providers import llm

    def _must_not_call(*a, **kw):
        raise AssertionError("无证据时不应调用 LLM")

    monkeypatch.setattr(llm, "chat", _must_not_call)

    project = indexed_doc["project"]
    # 不挂载任何 KB -> 无证据
    answer = rag_service.query(db, str(project.id), "Transformer 的注意力机制")
    assert answer.insufficient_evidence is True
    assert answer.citations == []
    assert answer.answer  # 有明确话术,不是空串


def test_query_with_evidence_returns_answer_and_citations(indexed_doc, db, monkeypatch, fake_milvus):
    from app.providers import llm

    monkeypatch.setattr(llm, "chat", lambda msgs, **kw: ("检索增强生成能缓解幻觉。", "fake-provider"))

    project = indexed_doc["project"]
    project_service.mount_kb(db, str(indexed_doc["user"].id), str(project.id), str(indexed_doc["kb"].id))
    answer = rag_service.query(db, str(project.id), "RAG 有什么用")
    assert answer.insufficient_evidence is False
    assert "幻觉" in answer.answer
    assert len(answer.citations) >= 1
    assert answer.provider == "fake-provider"


# ─────────────────────── 会话与引用持久化往返 ───────────────────────

def test_conversation_messages_persisted_with_citations(indexed_doc, db, monkeypatch, fake_redis, fake_milvus):
    """问答后:会话/消息/引用落库,可重新读取(规范 §13)。"""
    from app.providers import llm

    monkeypatch.setattr(llm, "chat", lambda msgs, **kw: ("RAG 通过外部知识缓解幻觉。", "fake-provider"))

    user, project = indexed_doc["user"], indexed_doc["project"]
    project_service.mount_kb(db, str(user.id), str(project.id), str(indexed_doc["kb"].id))

    result = conversation_service.answer(db, str(user.id), str(project.id), "RAG 的作用是什么")
    conv_id = result["conversation_id"]
    assert result["citations"]

    # 重新读取:用户消息 + 助手消息(带引用)都在
    messages = conversation_service.get_conversation_messages(db, str(user.id), conv_id)
    roles = [m.role.value if hasattr(m.role, "value") else str(m.role) for m in messages]
    assert roles == ["user", "assistant"]
    assistant = messages[-1]
    assert assistant.citations  # 引用持久化
    assert assistant.citations[0]["document_title"] == "综述.md"
    assert assistant.citations[0]["version_number"] == 1


def test_answer_stream_events_token_citations_done(indexed_doc, db, monkeypatch,
                                                   fake_redis, fake_milvus):
    """流式问答(SSE):事件序列 token -> citations -> done,引用真实,消息落库。"""
    import json

    from app.providers import llm

    monkeypatch.setattr(llm, "chat", lambda msgs, **kw: ("检索增强生成。", "fake-provider"))
    monkeypatch.setattr(llm, "chat_stream",
                        lambda msgs, **kw: iter(["检索增强生成", "能缓解幻觉。"]))

    user, project = indexed_doc["user"], indexed_doc["project"]
    project_service.mount_kb(db, str(user.id), str(project.id), str(indexed_doc["kb"].id))

    events = [
        json.loads(line.removeprefix("data: "))
        for chunk in conversation_service.answer_stream(
            db, str(user.id), str(project.id), "RAG 有什么用",
        )
        for line in chunk.strip().splitlines() if line.startswith("data: ")
    ]

    types = [e["type"] for e in events]
    assert "token" in types and "citations" in types
    assert types[-1] == "done"  # done 收尾
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert "缓解幻觉" in answer

    citations = next(e for e in events if e["type"] == "citations")
    conv_id = citations["conversation_id"]
    assert citations["citations"]
    assert citations["citations"][0]["document_title"] == "综述.md"  # 引用真实

    # 消息持久化:用户 + 助手(带引用)
    messages = conversation_service.get_conversation_messages(db, str(user.id), conv_id)
    assert [m.role.value for m in messages] == ["user", "assistant"]
    assert messages[-1].citations
