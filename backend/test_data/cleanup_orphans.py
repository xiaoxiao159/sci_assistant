"""清理 Milvus 孤儿向量:删除 PG 里已无 document 记录的向量(修复前残留 + 以后维护用)。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import milvus
from app.database.session import SessionLocal
from app.repositories import document_repo
from app.core.config import settings

c = milvus.get_client()
NAME = settings.MILVUS_COLLECTION

rows = c.query(NAME, filter='chunk_id != ""', output_fields=["document_id"], limit=10000)
doc_ids = set(r["document_id"] for r in rows)
print(f"Milvus 向量涉及 {len(doc_ids)} 个 document_id,共 {len(rows)} 条向量")

db = SessionLocal()
orphans = [did for did in doc_ids if document_repo.get(db, did) is None]
db.close()
print(f"其中 {len(orphans)} 个是孤儿(PG 无 document 记录)")

for did in orphans:
    milvus.delete_by_document(did)
    print(f"  删孤儿向量 document_id={did}")

if orphans:
    time.sleep(3)  # Milvus 一致性延迟
    remaining = c.query(NAME, filter='chunk_id != ""', output_fields=["document_id"], limit=10000)
    print(f"清理后剩余向量: {len(remaining)} 条")
else:
    print("无孤儿,不用清理")
