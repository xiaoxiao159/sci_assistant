"""MinIO 客户端:原始文档 blob 存储。

storage_key 指向 MinIO 里的对象,元数据在 PG(documents 表)。
"""
import io

from minio import Minio

from app.core.config import settings

_client: Minio | None = None


def get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


def ensure_bucket():
    c = get_client()
    if not c.bucket_exists(settings.MINIO_BUCKET):
        c.make_bucket(settings.MINIO_BUCKET)


def upload_bytes(object_key: str, data: bytes, content_type: str = "application/octet-stream"):
    c = get_client()
    c.put_object(settings.MINIO_BUCKET, object_key, io.BytesIO(data), len(data), content_type=content_type)


def download_bytes(object_key: str) -> bytes:
    c = get_client()
    obj = c.get_object(settings.MINIO_BUCKET, object_key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


def delete_object(object_key: str):
    c = get_client()
    c.remove_object(settings.MINIO_BUCKET, object_key)
