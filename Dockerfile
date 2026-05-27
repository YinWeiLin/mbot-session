FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（sentence-transformers 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 层缓存（依赖没变就不重新安装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 下载 embedding 模型（放在 COPY 代码之前，模型不变时走缓存不重新下载）
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-small-zh-v1.5', local_dir='data/models/bge-small-zh-v1.5')"

# 复制项目代码
COPY . .

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
