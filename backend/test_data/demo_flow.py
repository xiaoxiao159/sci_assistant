"""端到端演示:注册登录 -> 项目 -> 建知识库 -> 上传文档 ->
异步索引(真实 bge-m3 + Milvus) -> 挂载到项目 -> RAG 问答(真实 LLM,带引用)。

运行前提:后端 8001 + Celery worker 已启动;首次索引需加载 bge-m3(已缓存约 1 分钟内)。

    python test_data/demo_flow.py
"""
import io
import sys
import time

import requests

BASE = "http://127.0.0.1:8001/api/v1"

DEMO_MD = """# RAG 检索增强生成技术综述

## 1. 背景与动机

大语言模型(LLM)存在两个固有问题:知识截止(训练数据有截止日期)与幻觉(生成看似合理但无依据的内容)。检索增强生成(Retrieval-Augmented Generation, RAG)通过在生成前先从外部知识库检索相关证据,让模型"看着材料答题",从根本上缓解这两个问题。

## 2. 混合检索

生产级 RAG 系统普遍采用混合检索:同时执行稠密检索(语义向量,如 bge-m3)与稀疏检索(词法匹配,如 BM25),再用 RRF(Reciprocal Rank Fusion,倒数排序融合)合并两路排序结果。稠密检索擅长理解同义改写,稀疏检索擅长精确术语与人名编号,二者互补。检索时先取较大的候选池(如 top 50),交给重排阶段精选。

## 3. 重排序

粗排候选送入交叉编码器重排模型(如 bge-reranker-v2-m3)逐对打分,精选出最终 top_k(如 5)个片段。重排器比双塔向量更精细,但计算开销大,因此只在小候选集上执行。

## 4. 引用与溯源

可信的 RAG 回答必须附带引用:标明来源文档标题、版本号、页码与原文片段,并给出检索得分。证据不足时应明确拒答,而不是编造答案或伪造引用。

## 5. 索引流水线

离线索引流水线为:上传原件(MinIO 存储) -> 解析(PDF/Markdown/Word 抽取正文) -> 切片(默认 chunk_size=512 字符,重叠 64) -> 嵌入(bge-m3,稠密+稀疏双表示) -> 向量入库(Milvus,按知识库分区)。文档重新上传生成新版本,旧版本在新版本索引完成前保持可检索。
"""

QUESTION = "RAG 系统如何保证回答可信可溯源?切片默认参数是多少?"


def _items(payload):
    """列表端点兼容 {items: [...]} 与裸 [...] 两种形态。"""
    if isinstance(payload, dict):
        return payload.get("items", [])
    return payload


def main() -> int:
    s = requests.Session()

    # 1. 注册(重复运行时已存在则直接登录)
    r = s.post(f"{BASE}/auth/register", json={
        "username": "demo", "email": "demo@local.dev", "password": "demo123456"})
    print(f"[1] 注册 demo 用户: {r.status_code}")
    r = s.post(f"{BASE}/auth/login", json={"username": "demo", "password": "demo123456"})
    r.raise_for_status()
    token = r.json()["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    print("[2] 登录 OK")

    # 2. 项目(用户直属,重复运行时复用「演示项目」)
    projects = _items(s.get(f"{BASE}/projects").json())
    project = next((p for p in projects if p.get("name") == "演示项目"), None)
    if project is None:
        project = s.post(f"{BASE}/projects", json={"name": "演示项目", "description": "RAG 演示"}).json()
    print(f"[3] 项目「{project.get('name', project['id'])}」")

    # 3. 知识库 + 上传文档(触发异步索引任务)
    kb = s.post(f"{BASE}/knowledge_bases",
                json={"name": "演示知识库", "description": "RAG 综述演示"}).json()
    up = s.post(
        f"{BASE}/knowledge_bases/{kb['id']}/documents",
        files={"file": ("RAG综述.md", io.BytesIO(DEMO_MD.encode("utf-8")), "text/markdown")},
    )
    up.raise_for_status()
    doc = up.json()
    print(f"[4] 上传「{doc['filename']}」: doc={doc['document_id'][:8]}… "
          f"task={doc['task_id'][:8]}… 状态={doc['status']}")

    # 4. 轮询索引任务(首次需加载 bge-m3 模型)
    deadline = time.time() + 300
    status = doc["status"]
    while time.time() < deadline and status not in ("ready", "failed"):
        time.sleep(3)
        d = s.get(f"{BASE}/knowledge_bases/{kb['id']}/documents/{doc['document_id']}").json()
        status = d["status"]
        print(f"    索引中… status={status}", flush=True)
    if status != "ready":
        print("索引失败:", d.get("error_message"))
        return 1
    print(f"[5] 索引完成: {d['chunk_count']} 个切片, 当前版本 v{d['current_version_number']}")

    # 5. 挂载知识库到项目
    r = s.post(f"{BASE}/projects/{project['id']}/knowledge-bases",
               json={"knowledge_base_id": kb["id"]})
    print(f"[6] 挂载知识库到项目: {r.status_code}")

    # 6. 建会话并提问(真实 LLM + 重排 + 引用)
    conv = s.post(f"{BASE}/projects/{project['id']}/conversations",
                  json={"title": "RAG 演示会话"}).json()
    conv_id = conv.get("id") or conv.get("conversation_id")
    r = s.post(f"{BASE}/conversations/{conv_id}/messages",
               json={"question": QUESTION})
    r.raise_for_status()
    ans = r.json()
    print(f"\n[7] 问题: {QUESTION}")
    print(f"    证据不足拒答: {ans['insufficient_evidence']}")
    print(f"\n==== 回答 ====\n{ans['answer']}\n")
    print("==== 引用 ====")
    for i, c in enumerate(ans["citations"], 1):
        print(f"  [{i}] 《{c.get('document_title', '?')}》 v{c.get('version_number', '?')} "
              f"chunk={c.get('chunk_id', '?')[:8]}… score={c.get('score', 0):.3f}")
        print(f"      {c.get('snippet', '')[:60]}…")
    print(f"\n会话 {conv_id[:8]}… 已持久化,可在前端 http://localhost:5173 继续追问")
    return 0


if __name__ == "__main__":
    sys.exit(main())
