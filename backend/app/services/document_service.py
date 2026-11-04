"""文档业务(v8):版本化上传 + 索引任务编排。

上传流(规范 §11):
  ① API 校验文件(扩展名/MIME/大小)
  ② 文件写 MinIO,storage_key 带随机目录(不可预测)
  ③ 短事务:Document(+首版本)与 Task 落库
  ④ 提交后投递 Celery;Worker 认领任务 -> RAGService.index_document

版本语义:
  - 同名同内容(hash 相同):去重,不建新版本
  - 同名新内容:新版本;旧版本在新版本索引成功前保持可见(平滑换挡)
"""
import hashlib
import uuid

from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.exceptions import NotFoundError
from app.core.logger import logger
from app.models import DocumentStatus
from app.repositories import document_repo, knowledge_base_repo, task_repo
from app.services import knowledge_base_service
from app.storage import minio_client

INDEX_TASK_TYPE = "index_document"


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"


def _storage_key(kb_id: str, filename: str) -> str:
    # 文件名不直接作路径(防穿越):kbs/{kb}/{uuid}/{safe_name}
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"kbs/{kb_id}/{uuid.uuid4().hex}/{safe_name}"


def upload_document(
    db: Session, owner_id: str, kb_id: str, filename: str, content: bytes, content_type: str,
) -> tuple:
    """上传文档:鉴权 -> 去重/升版本 -> 存 MinIO -> 短事务建记录 -> 投递任务。

    返回 (document, version, is_dedup, task)。dedup 命中时 version 为当前版本、task 为 None。
    """
    kb = knowledge_base_service.get(db, owner_id, kb_id)  # 鉴权 + 取 KB

    file_hash = hashlib.sha256(content).hexdigest()
    existing = document_repo.get_by_original_filename(db, kb_id, filename)

    if existing is not None:
        # 同名同内容 -> 去重(不建版本,不重复索引)
        current = document_repo.get_current_version(db, existing)
        if current is not None and current.content_hash == file_hash:
            logger.info(f"文档命中内容去重,跳过重复入库: {filename}")
            return existing, current, True, None

    # 新文档 or 新版本:文件先落 MinIO
    storage_key = _storage_key(kb_id, filename)
    minio_client.upload_bytes(storage_key, content, content_type=content_type)

    if existing is None:
        doc = document_repo.create(
            db,
            knowledge_base_id=kb_id,
            owner_id=owner_id,
            title=filename,
            original_filename=filename,
            mime_type=content_type or "",
            file_size=len(content),
        )
        version_number = 1
    else:
        doc = existing
        version_number = max(v.version_number for v in doc.versions) + 1 if doc.versions else 1

    version = document_repo.create_version(
        db,
        document_id=str(doc.id),
        version_number=version_number,
        content_hash=file_hash,
        storage_key=storage_key,
        file_size=len(content),
        mime_type=content_type or "",
    )
    # 短事务:Document/Version/Task 一起提交
    task = task_repo.create(
        db,
        owner_id=owner_id,
        task_type=INDEX_TASK_TYPE,
        payload={"document_id": str(doc.id), "version_id": str(version.id)},
    )
    if existing is None:
        knowledge_base_repo.increment_doc_count(db, kb)
    db.commit()

    # 提交后投递(投递失败也没关系:恢复扫描会重新入队 pending 任务)
    _enqueue_index_task(str(task.id))
    logger.info(f"文档已上传并投递索引: {filename} -> doc={doc.id} v{version_number} task={task.id}")
    log_action(owner_id, "upload_doc", f"{filename} -> {doc.id} v{version_number}")
    return doc, version, False, task


def reindex_document(db: Session, owner_id: str, doc_id: str):
    """重新索引:以当前版本内容建新版本(记录新管线参数),旧版本索引成功前保持可见。"""
    doc = get_document(db, owner_id, doc_id)
    current = document_repo.get_current_version(db, doc)
    if current is None:
        raise NotFoundError("文档没有可用版本")

    version_number = max(v.version_number for v in doc.versions) + 1 if doc.versions else 1
    version = document_repo.create_version(
        db,
        document_id=str(doc.id),
        version_number=version_number,
        content_hash=current.content_hash,
        storage_key=current.storage_key,  # 复用原件对象,不复制
        file_size=current.file_size,
        mime_type=current.mime_type,
    )
    task = task_repo.create(
        db,
        owner_id=owner_id,
        task_type=INDEX_TASK_TYPE,
        payload={"document_id": str(doc.id), "version_id": str(version.id)},
    )
    document_repo.update_status(db, doc, DocumentStatus.uploaded)
    db.commit()
    _enqueue_index_task(str(task.id))
    log_action(owner_id, "reindex_doc", f"{doc_id} -> v{version_number}")
    return doc, version


def _enqueue_index_task(task_id: str) -> None:
    """投递 Celery(函数内导入,避免 services<->workers 循环引用)。"""
    from app.workers.tasks import process_index_task

    try:
        process_index_task.delay(task_id)
    except Exception as e:  # noqa: BLE001 - 投递失败靠恢复扫描兜底
        logger.warning(f"任务投递失败(等待恢复扫描): {e}")


# ─────────────────────── 查询 ───────────────────────

def get_document(db: Session, owner_id: str, doc_id: str):
    doc = document_repo.get(db, doc_id)
    if doc is None:
        raise NotFoundError("文档不存在")
    # 通过 KB 鉴权:文档所属 KB 必须是 owner 的
    knowledge_base_service.get(db, owner_id, str(doc.knowledge_base_id))
    return doc


def list_documents(db: Session, owner_id: str, kb_id: str):
    knowledge_base_service.get(db, owner_id, kb_id)  # 鉴权
    return document_repo.list_by_kb(db, kb_id)


def list_versions(db: Session, owner_id: str, doc_id: str):
    get_document(db, owner_id, doc_id)  # 鉴权
    return document_repo.list_versions(db, doc_id)


def get_chunks(db: Session, owner_id: str, doc_id: str):
    """取当前版本的切片(切分可视化用)。鉴权同 get_document。"""
    from app.repositories import chunk_repo

    doc = get_document(db, owner_id, doc_id)
    current = document_repo.get_current_version(db, doc)
    if current is None:
        return []
    return chunk_repo.get_by_version(db, str(current.id))


def get_content(db: Session, owner_id: str, doc_id: str) -> dict:
    """取当前版本解析后全文(源文件预览)。

    优先读 MinIO 里处理时存的 .parsed 全文;未存则重新解析原件(并缓存)。
    """
    from app.rag.ingestion import parser

    doc = get_document(db, owner_id, doc_id)
    current = document_repo.get_current_version(db, doc)
    if current is None:
        raise NotFoundError("文档没有可用版本")
    parsed_key = f"{current.storage_key}.parsed"
    try:
        text = minio_client.download_bytes(parsed_key).decode("utf-8", errors="ignore")
    except Exception:
        # 缓存未命中(旧文档),重新解析原件
        logger.info(f"解析全文缓存未命中,重新解析: {doc.original_filename}")
        content = minio_client.download_bytes(current.storage_key)
        text = parser.router.parse(content, doc.original_filename).full_text
        try:
            minio_client.upload_bytes(parsed_key, text.encode("utf-8"), "text/plain")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"缓存解析全文失败(忽略): {e}")
    return {
        "filename": doc.original_filename,
        "title": doc.title,
        "version_number": current.version_number,
        "text": text,
    }


def download_file(db: Session, owner_id: str, doc_id: str) -> tuple:
    """下载当前版本原件(返回 bytes + 文件名 + MIME)。"""
    doc = get_document(db, owner_id, doc_id)
    current = document_repo.get_current_version(db, doc)
    if current is None:
        raise NotFoundError("文档没有可用版本")
    content = minio_client.download_bytes(current.storage_key)
    return content, doc.original_filename, doc.mime_type or _ext(doc.original_filename)


# ─────────────────────── 删除 ───────────────────────

def delete_document(db: Session, owner_id: str, doc_id: str):
    """删文档:清 MinIO 各版本对象 + Milvus 向量 + PG 级联(versions/chunks)。

    幂等:重复删除第二次时文档已不存在(404),不会产生孤儿。
    """
    from app.database import milvus

    doc = get_document(db, owner_id, doc_id)
    kb = knowledge_base_repo.get(db, str(doc.knowledge_base_id))
    log_action(owner_id, "delete_doc", f"{doc.title} ({doc_id})")

    # 清三处:MinIO(各版本原件 + .parsed,storage_key 去重)+ Milvus + PG
    keys = {v.storage_key for v in doc.versions}
    keys |= {f"{k}.parsed" for k in keys}
    for key in keys:
        try:
            minio_client.delete_object(key)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"删除 MinIO 对象失败(忽略): {e}")
    try:
        milvus.delete_by_document(str(doc.id))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"删除 Milvus 向量失败(忽略): {e}")
    document_repo.delete(db, doc)  # CASCADE: versions -> chunks
    if kb is not None:
        knowledge_base_repo.increment_doc_count(db, kb, delta=-1)
    db.commit()
