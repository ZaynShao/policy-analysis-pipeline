"""共享 fixture for l1_collect 测试。"""
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _isolate_fetch_proxy_env(monkeypatch):
    """测试默认无代理 env;需要时各测试自行 setenv。"""
    monkeypatch.delenv("POLICY_FETCH_PROXY_URL", raising=False)


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """临时 state/ 目录,模拟 pipeline state 结构。"""
    (tmp_path / "T1_channels").mkdir(parents=True)
    (tmp_path / "T1_scan_raw").mkdir()
    (tmp_path / "T1_candidate").mkdir()
    return tmp_path


@pytest.fixture
def sample_catalog_yaml() -> str:
    return """\
- city: 杭州市
  province: 浙江省
  level: 市
  city_code: '330100'
  channel_type: 发改委
  root_domain: fgw.hangzhou.gov.cn
  list_url: https://fgw.hangzhou.gov.cn/col/col1229453592/index.html
  source: vault_catalog
  status: 验证
  last_probed_at: '2026-05-19T10:00:00'
  probe_result: ok
  notes: ''
"""
