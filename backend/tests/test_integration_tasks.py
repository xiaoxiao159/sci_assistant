"""集成测试(真实 PG):任务领取原子性、重试规则、恢复扫描(规范 §13)。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models import TaskStatus
from app.repositories import task_repo
from app.services import task_service

pytestmark = pytest.mark.integration


@pytest.fixture
def task(make_user, db):
    user = make_user("task-owner@t.cn")
    t = task_repo.create(
        db, owner_id=str(user.id), task_type="index_document",
        payload={"document_id": "d1", "version_id": "v1"},
    )
    db.commit()
    return user, t


# ─────────────────────── 原子领取 ───────────────────────

def test_claim_once_only(task, db):
    _, t = task
    first = task_repo.claim(db, str(t.id))
    assert first is not None and first.status == TaskStatus.running
    assert first.attempt_count == 1
    # 第二次领取(另一 Worker)返回 None:不重复执行
    assert task_repo.claim(db, str(t.id)) is None


def test_claim_nonexistent_or_terminal(task, db):
    _, t = task
    assert task_repo.claim(db, "00000000-0000-0000-0000-000000000000") is None
    task_repo.claim(db, str(t.id))
    task_repo.finish(db, task_repo.get(db, str(t.id)), TaskStatus.succeeded)
    db.commit()
    assert task_repo.claim(db, str(t.id)) is None  # 已终态不能再领


# ─────────────────────── 查询与所有权 ───────────────────────

def test_get_task_owner_scoped(task, db, make_user):
    owner, t = task
    other = make_user("other@t.cn")
    with pytest.raises(NotFoundError):
        task_service.get_task(db, str(other.id), str(t.id))
    got = task_service.get_task(db, str(owner.id), str(t.id))
    assert str(got.id) == str(t.id)


def test_list_tasks_filters_by_status(task, db):
    owner, t = task
    items = task_service.list_tasks(db, str(owner.id), status="pending")
    assert len(items) == 1
    items = task_service.list_tasks(db, str(owner.id), status="succeeded")
    assert items == []


# ─────────────────────── 受控重试 ───────────────────────

def test_retry_only_failed(task, db):
    owner, t = task
    # pending 不能重试
    with pytest.raises(ConflictError):
        task_service.retry_task(db, str(owner.id), str(t.id))
    # succeeded 也不能
    claimed = task_repo.claim(db, str(t.id))
    task_repo.finish(db, claimed, TaskStatus.succeeded)
    db.commit()
    with pytest.raises(ConflictError):
        task_service.retry_task(db, str(owner.id), str(t.id))


def test_retry_failed_within_max_attempts(task, db):
    owner, t = task
    claimed = task_repo.claim(db, str(t.id))
    task_repo.finish(db, claimed, TaskStatus.failed, error_code="boom", error_message="测试失败")
    db.commit()
    retried = task_service.retry_task(db, str(owner.id), str(t.id))
    assert retried.status == TaskStatus.pending
    assert retried.attempt_count == 1  # 重试不增加本次尝试,领取时才 +1


def test_retry_blocked_after_max_attempts(task, db):
    owner, t = task
    for _ in range(t.max_attempts):
        claimed = task_repo.claim(db, str(t.id))
        task_repo.finish(db, claimed, TaskStatus.failed, error_code="boom", error_message="失败")
        db.commit()
        if task_repo.get(db, str(t.id)).attempt_count < t.max_attempts:
            task_service.retry_task(db, str(owner.id), str(t.id))
    with pytest.raises(ConflictError, match="最大尝试次数"):
        task_service.retry_task(db, str(owner.id), str(t.id))


# ─────────────────────── 恢复扫描 ───────────────────────

def test_sweep_requeues_stale_running(task, db, no_enqueue):
    owner, t = task
    task_repo.claim(db, str(t.id))  # running
    db.commit()
    # 模拟僵死:updated_at 拨回 1 小时前
    from sqlalchemy import update
    from app.models import Task

    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    db.execute(update(Task).where(Task.id == t.id).values(updated_at=stale))
    db.commit()

    requeued = task_service.sweep_stale_tasks(stale_minutes=10)
    assert str(t.id) in requeued
    assert task_repo.get(db, str(t.id)).status == TaskStatus.pending


def test_sweep_ignores_fresh_running(task, db, no_enqueue):
    _, t = task
    task_repo.claim(db, str(t.id))
    db.commit()
    requeued = task_service.sweep_stale_tasks(stale_minutes=10)
    assert requeued == []
    assert task_repo.get(db, str(t.id)).status == TaskStatus.running


# ─────────────────────── 任务事件流 ───────────────────────

def test_task_events_recorded(task, db):
    _, t = task
    task_repo.add_event(db, str(t.id), "running", "attempt 1")
    task_repo.add_event(db, str(t.id), "succeeded")
    db.commit()
    events = task_repo.get(db, str(t.id)).events
    assert [e.status for e in events] == ["running", "succeeded"]
