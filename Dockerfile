FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml constraints.txt ./
# 依赖层:与 scripts 解耦,改代码不再触发依赖解析。依赖清单须与 pyproject 同步维护。
RUN grep -vE '^-e ' constraints.txt > /tmp/constraints.pip && pip install --no-cache-dir -c /tmp/constraints.pip pyyaml "anthropic>=0.40" "psycopg2-binary>=2.9" trafilatura beautifulsoup4 requests
COPY scripts ./scripts
RUN pip install --no-cache-dir --no-deps -e .
# vault 与 state 运行时挂载,不进镜像
ENV PYTHONUNBUFFERED=1
