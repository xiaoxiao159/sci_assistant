"""API 层:薄路由。接请求 -> 调 service -> 返响应。

铁律:不直接访问 DB(走 service/repo),不写业务逻辑。
"""
