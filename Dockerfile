FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .
# vault 与 state 运行时挂载,不进镜像
ENV PYTHONUNBUFFERED=1
