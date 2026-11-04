"""验证源文件预览 + 下载 API。用 p04_user 已有的就绪文档。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE = "http://127.0.0.1:8001/api/v1"


def main():
    c = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    r = c.post("/auth/login", json={"username": "p04_user", "password": "secret123"})
    if r.status_code != 200:
        r = c.post("/auth/register", json={
            "username": "p04_user", "email": "p04@t.com", "password": "secret123"
        })
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    # 找一个有就绪文档的 KB
    kbs = c.get("/knowledge_bases").json()
    if not kbs:
        print("[FAIL] 无 KB,先跑 test_p0_4a_chunks.py 建一个"); return
    kb_id = kbs[0]["id"]
    docs = c.get(f"/knowledge_bases/{kb_id}/documents").json()
    ready = next((d for d in docs if d["status"] == "ready"), None)
    if not ready:
        print("[FAIL] 无就绪文档"); return
    doc_id = ready["id"]
    print(f"测试文档: {ready['filename']} (doc_id={doc_id[:8]}..)")

    # ★ 测预览(content)
    r = c.get(f"/knowledge_bases/{kb_id}/documents/{doc_id}/content")
    print(f"\nGET /content: HTTP {r.status_code}")
    data = r.json()
    print(f"  filename={data['filename']} file_type={data['file_type']}")
    print(f"  text 长度={len(data['text'])} 字符")
    print(f"  text 预览: {data['text'][:80]}...")
    ok_content = r.status_code == 200 and len(data["text"]) > 0

    # ★ 测下载(download)
    r = c.get(f"/knowledge_bases/{kb_id}/documents/{doc_id}/download")
    print(f"\nGET /download: HTTP {r.status_code}, content-type={r.headers.get('content-type')}, 大小={len(r.content)} bytes")
    cd = r.headers.get("content-disposition", "")
    print(f"  content-disposition={cd}")
    ok_download = r.status_code == 200 and len(r.content) > 0 and "attachment" in cd

    print("\n[PASS] 源文件预览+下载验证通过" if ok_content and ok_download
          else f"\n[FAIL] content_ok={ok_content} download_ok={ok_download}")


if __name__ == "__main__":
    main()
