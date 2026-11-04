"""RAG 评估模块:评测集 + 指标(检索 Recall + 生成 正确性/忠实性/相关性)。

用 LLM-as-judge(项目自己的 llm)评生成质量,避免 RAGAS 依赖冲突。
检索指标(Recall)自算。后续可接 RAGAS 对比。
"""
