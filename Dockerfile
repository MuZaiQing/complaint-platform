# 一键部署：前端 index.html + FastAPI 同进程提供服务
# 构建:  docker compose up -d --build
# 单独构建: docker build -t complaint-platform . && docker run -p 8000:8000 -v "$PWD:/data:ro" complaint-platform
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_ROOT=/data

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 只拷后端代码/模型/静态资源；大体积 CSV、pkl 通过 /data 卷挂载
COPY backend/ ./

EXPOSE 8000

# 单 worker：明细数据与模型在进程内缓存，多 worker 会成倍占内存
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
