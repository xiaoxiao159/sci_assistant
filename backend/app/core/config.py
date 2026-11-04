"""配置中心(从 .env 读,绝对路径定位)。

所有可配置项集中在此。pydantic-settings 自动按字段名读环境变量/.env。
新增配置项时:在此加字段 + 在 .env.example 加示例。
"""
import os
from pathlib import Path

# HuggingFace 国内镜像(必须在导入 FlagEmbedding/transformers 前设置)。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
# 纯离线:模型已缓存,避免 BGEM3FlagModel 的 snapshot_download 去拉镜像上 403 的
# imgs/.DS_Store 等非必要文件。权重已在本地缓存(bge-m3 / bge-reranker-v2-m3)。
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> parent.parent.parent = backend/(.env 所在)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # ── 应用 ──
    APP_NAME: str = "sci_assistant"
    PORT: int = 8001
    DEBUG: bool = False

    # ── LLM(主/副由 LLM_PRIMARY 决定,主失败自动降级到副)──
    LLM_PRIMARY: str = "siliconflow"  # 主提供商:bailian | siliconflow
    BAILIAN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    BAILIAN_API_KEY: str = ""
    BAILIAN_MODEL: str = "qwen-plus"
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V3"
    LLM_TIMEOUT: int = 120

    # ── JWT 鉴权 ──
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    # ── PostgreSQL(关系元数据 + 切片正文)──
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "sci_assistant"

    # ── Redis(会话记忆 + Celery broker)──
    REDIS_URL: str = "redis://localhost:6379/0"
    SESSION_TTL: int = 60 * 60 * 24  # 会话短期记忆保留 24h

    # ── MinIO(原始文档 blob)──
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "sci_assistant"
    MINIO_SECURE: bool = False

    # ── Milvus(向量库)──
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "sci_assistant_chunks"

    # ── 检索参数 ──
    RETRIEVAL_TOP_K: int = 6          # 最终喂给 LLM 的 chunk 数
    RETRIEVAL_CANDIDATE: int = 20     # 每路召回候选数
    RRF_K: int = 60                   # RRF 融合常数
    USE_HYDE: bool = False            # P2-6: HyDE(假设答案向量检索,开=True 增加一次 LLM 调用)

    # ── 文档解析(router 模式)──
    PARSER_MODE: str = "router"       # router | api_only | local_only
    MINERU_API_URL: str = ""
    MINERU_API_TOKEN: str = ""

    # ── 切片 ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # ── Embedding / Reranker(本地 bge 系列)──
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    # HuggingFace 国内镜像(在 main.py 顶部生效,这里仅记录默认值)
    HF_ENDPOINT: str = "https://hf-mirror.com"

    # ── MCP 对外工具服务(规范 §9)──
    MCP_TRANSPORT: str = "stdio"            # stdio | http(streamable-http)
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8002
    # API Key 与用户绑定:"key1:email1,key2:email2";空 = 拒绝所有外部调用
    MCP_API_KEYS: str = ""
    MCP_ENABLE_WRITE_TOOLS: bool = False    # index_document 等写工具默认关
    MCP_RATE_LIMIT: int = 30                # 每 key 每分钟总调用上限
    MCP_QUERY_RATE_LIMIT: int = 10          # query(耗 LLM)单独更严
    MCP_MAX_CONTENT_CHARS: int = 8000       # get_document_content 输出字符上限


settings = Settings()
