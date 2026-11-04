"""枚举集中定义(v8)。"""
import enum


class KBStatus(str, enum.Enum):
    """知识库状态:archived 的 KB 不参与检索(可再激活)。"""
    active = "active"
    archived = "archived"


class DocumentStatus(str, enum.Enum):
    """文档状态(文档级聚合视图,反映当前版本摄入情况)。"""
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class VersionStatus(str, enum.Enum):
    """文档版本索引状态。indexed 的版本才可被检索;superseded 为历史版本。"""
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"
    superseded = "superseded"


class TaskStatus(str, enum.Enum):
    """异步任务状态机:pending -> running -> succeeded/failed。"""
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
