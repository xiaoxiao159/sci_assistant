"""RAG 链路端到端冒烟:注册 -> KB -> 上传文档 -> 摄入 ready -> 项目 -> 挂载 KB。

运行:python tests/e2e_part_a.py (需 API + Celery worker 已启动)
"""
import sys
import time

import httpx

BASE = "http://127.0.0.1:8001/api/v1"
# trust_env=False:不走系统代理(本机直连;开着 Clash 时系统代理会把 127.0.0.1 也劫走 -> 502)
client = httpx.Client(base_url=BASE, timeout=30, trust_env=False)


def main() -> int:
    ts = str(int(time.time()))
    username = f"e2e_a_{ts}"

    r = client.post("/auth/register", json={"username": username, "email": f"{username}@t.cn", "password": "passw0rd!"})
    assert r.status_code in (200, 201), r.text
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print(f"[1] 注册登录 OK: {username}")

    r = client.post("/knowledge_bases", json={"name": f"e2e-kb-{ts}", "description": "RAG 链路冒烟"})
    kb_id = r.json()["id"]
    print(f"[2] KB 创建 OK: {kb_id}")

    with open("test_data/sample.md", "rb") as f:
        r = client.post(
            f"/knowledge_bases/{kb_id}/documents",
            files={"file": ("sample.md", f, "text/markdown")},
        )
    assert r.status_code in (200, 201), r.text
    doc_id = r.json()["document_id"]
    print(f"[3] 文档上传 OK: {doc_id}(Celery 异步摄入)")

    r = client.post("/projects", json={"name": f"e2e-proj-{ts}"})
    assert r.status_code in (200, 201), r.text
    project_id = r.json()["id"]
    print(f"[4] 项目创建 OK: {project_id}")

    r = client.put(f"/projects/{project_id}/knowledge-bases", json={"knowledge_base_ids": [kb_id]})
    assert r.status_code == 200, r.text
    print("[5] KB 挂载 OK")

    # 等文档摄入完成(嵌入本地模型,需一会儿)
    for _ in range(60):
        r = client.get(f"/knowledge_bases/{kb_id}/documents/{doc_id}")
        if r.json().get("status") == "ready":
            print("[6] 文档摄入完成(status=ready)")
            break
        time.sleep(2)
    else:
        print("[!] 文档未 ready,请检查 worker 日志")
        return 1

    print("=== RAG 链路 e2e 通过 ===")
    print(f"project_id={project_id}(可用于手工问答验证)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
