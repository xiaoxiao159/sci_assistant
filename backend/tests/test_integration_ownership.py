"""集成测试(真实 PG):所有权隔离、挂载约束、409 删除(规范 §13)。

跨用户读写一律拒绝;跨用户挂载被拒;重复挂载幂等;被挂载 KB 删除 409;
数据库层约束(复合外键)兜底。
"""
import pytest
from sqlalchemy import text

from app.core.exceptions import ConflictError, NotFoundError
from app.services import (
    conversation_service,
    knowledge_base_service,
    project_service,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def two_users(make_user, make_project, make_kb):
    """用户 A/B 各自的完整资源树。"""
    a = make_user("a@t.cn")
    b = make_user("b@t.cn")
    proj_a = make_project(str(a.id), "proj-a")
    proj_b = make_project(str(b.id), "proj-b")
    kb_a = make_kb(str(a.id), "kb-a")
    kb_b = make_kb(str(b.id), "kb-b")
    return {"a": a, "b": b,
            "proj_a": proj_a, "proj_b": proj_b, "kb_a": kb_a, "kb_b": kb_b}


# ─────────────────────── 跨用户读写隔离 ───────────────────────

def test_user_b_cannot_read_a_project(two_users, db):
    with pytest.raises(NotFoundError):
        project_service.get(db, str(two_users["b"].id), str(two_users["proj_a"].id))


def test_user_b_cannot_read_a_kb(two_users, db):
    with pytest.raises(NotFoundError):
        knowledge_base_service.get(db, str(two_users["b"].id), str(two_users["kb_a"].id))


def test_user_b_cannot_update_a_kb(two_users, db):
    from app.schemas.knowledge_base import KbUpdate

    with pytest.raises(NotFoundError):
        knowledge_base_service.update(
            db, str(two_users["b"].id), str(two_users["kb_a"].id),
            KbUpdate(name="被改掉的名字"),
        )
    # A 的 KB 名字没变
    kb = knowledge_base_service.get(db, str(two_users["a"].id), str(two_users["kb_a"].id))
    assert kb.name == "kb-a"


# ─────────────────────── 挂载约束 ───────────────────────

def test_cross_user_mount_rejected(two_users, db):
    """B 的项目挂 A 的 KB -> 服务层拒绝(404,不泄露存在性)。"""
    with pytest.raises(NotFoundError):
        project_service.mount_kb(db, str(two_users["b"].id), str(two_users["proj_b"].id), str(two_users["kb_a"].id))


def test_cross_user_mount_blocked_at_db_level(two_users, db):
    """绕过服务层直接写挂载表:数据库复合外键拒绝(纵深防御)。"""
    with pytest.raises(Exception):
        db.execute(text(
            "INSERT INTO project_knowledge_bases (project_id, knowledge_base_id, owner_id) "
            "VALUES (:p, :k, :o)"
        ), {"p": str(two_users["proj_b"].id), "k": str(two_users["kb_a"].id), "o": str(two_users["b"].id)})
        db.commit()
    db.rollback()


def test_same_user_mount_and_duplicate_idempotent(two_users, db):
    a, proj, kb = str(two_users["a"].id), str(two_users["proj_a"].id), str(two_users["kb_a"].id)
    project_service.mount_kb(db, a, proj, kb)
    project_service.mount_kb(db, a, proj, kb)  # 重复挂载
    mounted = project_service.list_mounted_kbs(db, a, proj)
    assert [str(k.id) for k in mounted] == [kb]  # 不重复写入


def test_mounted_kb_delete_returns_409(two_users, db):
    a, proj, kb = str(two_users["a"].id), str(two_users["proj_a"].id), str(two_users["kb_a"].id)
    project_service.mount_kb(db, a, proj, kb)
    with pytest.raises(ConflictError):
        knowledge_base_service.delete(db, a, kb)


def test_unmount_then_delete_ok(two_users, db):
    a, proj, kb = str(two_users["a"].id), str(two_users["proj_a"].id), str(two_users["kb_a"].id)
    project_service.mount_kb(db, a, proj, kb)
    project_service.unmount_kb(db, a, proj, kb)
    knowledge_base_service.delete(db, a, kb)  # 解除挂载后可删
    with pytest.raises(NotFoundError):
        knowledge_base_service.get(db, a, kb)


# ─────────────────────── 会话归属 ───────────────────────

def test_conversation_owner_must_match_project(two_users, db, fake_redis):
    """B 在 A 的项目下建会话 -> 拒绝(owner 与 project owner 不一致被拦)。"""
    with pytest.raises(NotFoundError):
        conversation_service.create_conversation(
            db, str(two_users["b"].id), str(two_users["proj_a"].id), title="越权会话"
        )


def test_user_b_cannot_read_a_conversation(two_users, db, fake_redis):
    a = str(two_users["a"].id)
    conv = conversation_service.create_conversation(db, a, str(two_users["proj_a"].id), title="A 的会话")
    with pytest.raises(NotFoundError):
        conversation_service.get_conversation(
            db, str(two_users["b"].id), str(two_users["proj_a"].id), str(conv.id)
        )
    with pytest.raises(NotFoundError):
        conversation_service.get_conversation_messages(db, str(two_users["b"].id), str(conv.id))
