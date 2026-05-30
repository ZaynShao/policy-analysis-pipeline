"""共享 fixture for l1_audit 测试。"""
import textwrap
import pytest


def _policy_md(fm_yaml: str, body: str = "## 政策原文\n正文内容。") -> str:
    return f"---\n{fm_yaml.strip()}\n---\n\n{body}\n"


@pytest.fixture
def vault_policies(tmp_path):
    d = tmp_path / "0_raw" / "policies"
    d.mkdir(parents=True)
    (d / "good.md").write_text(_policy_md(textwrap.dedent("""
        id: P_2025_NDRC_357_a
        title: 关于加快推进虚拟电厂发展的指导意见
        official_number: 发改能源〔2025〕357号
        date: '2025-03-01'
        issuer: 国家发展和改革委员会
        issuer_canonical: [ndrc]
        provenance:
          url: https://www.ndrc.gov.cn/a/2025-03-01/x.html
        region:
          level: 国家
    """)), encoding="utf-8")
    return d
