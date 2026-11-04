"""Service 层:业务逻辑 + 编排。

职责:调 repository(CRUD)、storage(MinIO/Redis)、providers(LLM/Embedding)、rag、workers。
不含:原始 SQL(走 repo)、HTTP 细节(那是 api 层)。
"""
