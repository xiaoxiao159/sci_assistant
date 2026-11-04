"""诊断 Milvus delete_by_document 是否真生效(排除一致性延迟)。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import milvus
from app.core.config import settings

c = milvus.get_client()
NAME = settings.MILVUS_COLLECTION

# 查所有向量(用 chunk_id 非空做宽过滤)
rows = c.query(NAME, filter='chunk_id != ""', output_fields=["chunk_id", "document_id"], limit=100)
print(f"当前 Milvus 向量数: {len(rows)}")
for r in rows[:5]:
    print(f"  chunk_id={r.get('chunk_id')[:8]}.. document_id={r.get('document_id')[:8]}..")

if not rows:
    print("无向量,无需测"); sys.exit()

# 取第一个,试着删
target_doc = rows[0]["document_id"]
print(f"\n对 document_id={target_doc} 调 delete_by_document...")
milvus.delete_by_document(target_doc)
print("删除调用完成(无异常)")

# 立即查
for delay in [0, 2, 5]:
    time.sleep(delay if delay else 0)
    after = c.query(NAME, filter=f'document_id == "{target_doc}"', output_fields=["chunk_id"], limit=100)
    print(f"  等 {delay}s 后查: {len(after)} 条")
