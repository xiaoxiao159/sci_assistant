# sci_assistant 后端镜像(API + Celery worker 共用)
FROM python:3.12-slim

# 系统依赖(pymupdf / psycopg2 等需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖(利用 docker 层缓存)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY . .

# HuggingFace 国内镜像(构建期不下载模型,运行期 lazy 加载时生效)
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HUB_DISABLE_XET=1

EXPOSE 8001

# 默认起 API;Celery worker 在 docker-compose 里覆盖 command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
