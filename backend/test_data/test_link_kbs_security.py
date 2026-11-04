"""验证挂载安全:project 挂载 KB 校验归属,防数据泄露。

与 tests/test_integration_ownership.py 的服务层用例互补:这里走真实 HTTP
+ 真实 token,验证 API 层鉴权一致。
"""
import httpx

BASE = "http://127.0.0.1:8001/api/v1"


def main():
    c = httpx.Client(base_url=BASE, timeout=60, trust_env=False)

    # 两个用户(用唯一用户名避免和老数据冲突)
    def reg(name):
        r = c.post("/auth/register", json={
            "username": name, "email": f"{name}@p0test.com", "password": "secret123"
        })
        r.raise_for_status()
        return r.json()["access_token"]

    alice_tok = reg("alice_p0")
    bob_tok = reg("bob_p0")

    # alice 建 KB_A + 项目,bob 建 KB_B
    c.headers["Authorization"] = f"Bearer {alice_tok}"
    r = c.post("/knowledge_bases", json={"name": "KB_A"})
    kb_a = r.json()["id"] if r.status_code < 400 else c.get("/knowledge_bases").json()[0]["id"]
    r = c.post("/projects", json={"name": "proj正常"})
    proj_id = r.json()["id"]

    c.headers["Authorization"] = f"Bearer {bob_tok}"
    r = c.post("/knowledge_bases", json={"name": "KB_B"})
    kb_b = r.json()["id"] if r.status_code < 400 else c.get("/knowledge_bases").json()[0]["id"]

    # 切回 alice
    c.headers["Authorization"] = f"Bearer {alice_tok}"

    print(f"alice 的 KB_A = {kb_a}")
    print(f"bob   的 KB_B = {kb_b}")
    print(f"alice 的项目  = {proj_id}")
    print("")

    # 测试1:alice 挂自己的 KB_A -> 应成功(201)
    r = c.post(f"/projects/{proj_id}/knowledge-bases", json={"knowledge_base_id": kb_a})
    print(f"[测试1] alice 挂自己的 KB_A: HTTP {r.status_code} (期望 201)")
    ok1 = r.status_code == 201

    # 测试2:alice 全量替换挂 bob 的 KB_B -> 应被拒(404,防泄露)
    r = c.put(f"/projects/{proj_id}/knowledge-bases", json={"knowledge_base_ids": [kb_b]})
    print(f"[测试2] alice 挂 bob 的 KB_B: HTTP {r.status_code} (期望 404,防泄露)")
    ok2 = r.status_code == 404

    # 测试3:alice 挂不存在的 kb_id -> 应 404
    r = c.put(f"/projects/{proj_id}/knowledge-bases",
              json={"knowledge_base_ids": ["00000000-0000-0000-0000-000000000000"]})
    print(f"[测试3] alice 挂不存在的 KB: HTTP {r.status_code} (期望 404)")
    ok3 = r.status_code == 404

    # 测试4:确认挂载关系没被污染(应该只有 KB_A)
    r = c.get(f"/projects/{proj_id}/knowledge-bases")
    mounted = [m["knowledge_base_id"] for m in r.json()]
    print(f"[测试4] 当前挂载的 KBs = {mounted} (应只有 KB_A,不含 KB_B)")
    ok4 = kb_b not in mounted and kb_a in mounted

    print("")
    if ok1 and ok2 and ok3 and ok4:
        print("[PASS] 挂载安全验证通过:mount 校验 KB 归属,数据泄露已堵")
    else:
        print(f"[FAIL] 有项未通过: ok1={ok1} ok2={ok2} ok3={ok3} ok4={ok4}")


if __name__ == "__main__":
    main()
