"""RAG 评估运行器:加载评测集 -> 跑 RAG -> 算指标 -> 出报告。

指标:
  - 检索 Recall@k:相关文档是否在召回结果里(自算)
  - 生成 正确性/忠实性/相关性:LLM-as-judge(用项目自己的 llm)
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EvalCase:
    """一条评测用例。"""
    question: str
    expected_answer: str
    relevant_doc_filename: str   # 相关文档名(检索 Recall 判定用)


def load_eval_set(path: str | Path) -> list[EvalCase]:
    """从 JSON 加载评测集。格式:[{question, expected_answer, relevant_doc_filename}]"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [EvalCase(**c) for c in data]


# ── 指标 ──

def _llm_judge(prompt: str) -> float:
    """LLM 判 是/否 -> 1.0/0.0。失败返回 -1(不计入平均)。"""
    from app.providers import llm
    try:
        ans, _ = llm.chat(
            [llm.ChatMessage(role="user", content=prompt)],
            temperature=0.0, max_tokens=16,
        )
        return 1.0 if "是" in ans.strip() else 0.0
    except Exception:
        return -1.0


def retrieval_recall(citations, relevant_doc_filename: str) -> float:
    """检索 Recall:相关文档是否在召回结果里。citations 是引用 dict 列表。"""
    return 1.0 if any(
        (c.get("document_title") or "") == relevant_doc_filename for c in citations
    ) else 0.0


def judge_correctness(question: str, expected: str, actual: str) -> float:
    """答案正确性:是否含标准答案关键信息。"""
    return _llm_judge(
        f"问题:{question}\n标准答案:{expected}\n实际答案:{actual}\n"
        f"实际答案是否包含标准答案的关键信息且正确?只答'是'或'否'。"
    )


def judge_faithfulness(actual: str, context_snippets: list[str]) -> float:
    """忠实性:答案是否基于资料(不幻觉)。"""
    context = "\n".join(context_snippets) or "(无资料)"
    return _llm_judge(
        f"参考资料:{context}\n答案:{actual}\n"
        f"答案是否完全基于参考资料(无编造)?只答'是'或'否'。"
    )


def judge_relevancy(question: str, actual: str) -> float:
    """相关性:答案是否切题。"""
    return _llm_judge(
        f"问题:{question}\n答案:{actual}\n答案是否切题回答了问题?只答'是'或'否'。"
    )


# ── 运行 ──

def run_eval(db, owner_id: str, project_id: str, cases: list[EvalCase]) -> dict:
    """对评测集跑 RAG(项目级),算指标,返回 {cases, summary}。"""
    from app.services import conversation_service

    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {case.question}")
        try:
            resp = conversation_service.answer(db, owner_id, project_id, case.question)
        except Exception as e:  # noqa: BLE001
            results.append({"question": case.question, "error": str(e)})
            continue

        citations = resp["citations"]
        # 取完整切片正文(faithfulness 需要完整上下文,snippet 只有 120 字会误判)
        from app.repositories import chunk_repo
        chunk_ids = [c["chunk_id"] for c in citations]
        full_chunks = chunk_repo.get_by_ids(db, chunk_ids)
        context_texts = [c.text for c in full_chunks]

        rec = retrieval_recall(citations, case.relevant_doc_filename)
        cor = judge_correctness(case.question, case.expected_answer, resp["answer"])
        fai = judge_faithfulness(resp["answer"], context_texts)
        rel = judge_relevancy(case.question, resp["answer"])
        results.append({
            "question": case.question,
            "answer": resp["answer"],
            "expected": case.expected_answer,
            "relevant_doc": case.relevant_doc_filename,
            "num_sources": len(citations),
            "retrieval_recall": rec,
            "correctness": cor,
            "faithfulness": fai,
            "relevancy": rel,
        })

    # 汇总(排除 -1 失败项)
    def avg(key):
        vals = [r[key] for r in results if key in r and isinstance(r[key], (int, float)) and r[key] >= 0]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    summary = {
        "num_cases": len(cases),
        "retrieval_recall": avg("retrieval_recall"),
        "correctness": avg("correctness"),
        "faithfulness": avg("faithfulness"),
        "relevancy": avg("relevancy"),
    }
    return {"cases": results, "summary": summary}
