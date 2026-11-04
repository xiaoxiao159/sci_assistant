"""审计日志(P2-5):记录关键操作(谁、做了什么、何时)。

企业合规用:登录/上传/删除/提问等关键操作留痕。
v1 写到 logger(结构化),后续可接 ELK 或审计表。
"""
from app.core.logger import logger


def log_action(user_id: str, action: str, detail: str = "") -> None:
    """记录审计日志。user_id + action + detail + 时间(logger 自带时间)。"""
    logger.info(f"[AUDIT] user={user_id} action={action} detail={detail}")
