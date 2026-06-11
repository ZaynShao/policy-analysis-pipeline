# Codex 交接：WP-6d 构建可重复性（本地代码 + 服务器验证，一包）

**背景**：今天镜像重建两次被 pip 咬：①加 git 层使缓存失效→全新解析撞 PyPI 网络超时出假性 ResolutionImpossible；②每次 `COPY scripts` 都使 `pip install -e .` 层失效→每改一行 python 就重新解析依赖。两个根因：依赖无锁 + Dockerfile 层序。

**素材**：`docs/handoffs/wp6d-image-pip-freeze-20260611.txt`（39 行，**当前服务器已知好镜像的 pip freeze**，作为锁定源）。

**纪律（红线，违者中止）**：只许新建 `constraints.txt` + 改 `Dockerfile` + 移动/重命名上述素材文件；不碰 vault/产线；服务器上只做镜像构建与验证（test tag 先行），不动容器/cron/state；任何验证不过停下原样报告。无 pytest 要求（无 python 改动），验证=构建闸。

**分支**：`wp6/build-repro`（从 main 最新起）。

## 改动 1 · `constraints.txt`（仓库根）

内容=素材 freeze 全量（39 行），文件头注释：来源（2026-06-11 服务器镜像 freeze）、更新方式（升级依赖时重生成）。素材文件移正为它（docs/handoffs 下那份删除或保留皆可，说明即可）。

## 改动 2 · Dockerfile 层序

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml constraints.txt ./
# 依赖层:与 scripts 解耦,改代码不再触发依赖解析。依赖清单须与 pyproject 同步维护。
RUN pip install --no-cache-dir -c constraints.txt pyyaml "anthropic>=0.40" "psycopg2-binary>=2.9" trafilatura beautifulsoup4 requests
COPY scripts ./scripts
RUN pip install --no-cache-dir --no-deps -e .
ENV PYTHONUNBUFFERED=1
```

## 服务器验证（test tag 先行，不动 :latest）

```bash
ssh ... root@8.216.59.173
cd /root/policy-pipeline-src && git fetch --depth=1 origin <分支推到 origin? 不——> 
```
**注意**：分支不推远端。验证方式：scp 仅 `Dockerfile`+`constraints.txt`+`pyproject.toml` 到服务器临时目录 `/tmp/wp6d-build-test/`，加上 `rsync`/`scp -r` 当前 `scripts/`（或直接 `git archive HEAD scripts | ssh ... tar -x -C /tmp/wp6d-build-test`），然后：

```bash
docker build -t policy-pipeline:repro-test /tmp/wp6d-build-test
docker run --rm policy-pipeline:repro-test git --version
docker run --rm policy-pipeline:repro-test python -c "import scripts.service.relations_increment, scripts.service.summaries_increment, scripts.derived_signals.run, scripts.sync.run_sync; print('IMPORTS_OK')"
docker run --rm policy-pipeline:repro-test pip check
docker run --rm policy-pipeline:repro-test pip freeze | diff - /tmp/wp6d-build-test/constraints.txt 的非注释行   # 允许少量顺序差,逐行核对一致性
```

全过 → commit（单 commit 可，注明验证已在服务器以 repro-test tag 通过）；清理 `/tmp/wp6d-build-test` 与 repro-test 镜像 tag。**不重建 :latest**（留给下次正常部署随包生效）。

## 回报

stdout：分支、commit、服务器构建闸各项输出、pip freeze diff 结论。无需 report 文件。
