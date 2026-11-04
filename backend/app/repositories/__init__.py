"""Repository 层:纯 DB 操作(CRUD),一个实体一个 repo。

铁律:
  - 只做数据库读写,不含业务规则、不调 service/storage/provider。
  - 依赖只朝下:不 import app/services / app/api。
  - 函数签名第一参数固定为 db: Session(便于 service 编排时传入)。
"""
