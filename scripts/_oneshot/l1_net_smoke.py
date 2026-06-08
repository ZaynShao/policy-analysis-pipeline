"""L1 ops step-0 网络冒烟:钉实测数字定三件事——
  ① firecrawl/tavily/deepseek 三个外部依赖是否从本机可达
  ② BS4 直连国家级政府站的成功率(=plan Task10「国家级验证≥8」阈值是否现实)
  ③ probe 是否需要补 firecrawl(选C 命门:firecrawl 能否渲染 CN 政府页)
一次性诊断:不写 raw、不入 catalog。run:
  set -a; . ~/.config/policy-pipeline/models.env; set +a
  OPENAI_BASE_URL=https://api.deepseek.com OPENAI_API_KEY=$DEEPSEEK_API_KEY \
  JUDGE_MODEL=deepseek-v4-flash python3 -m scripts._oneshot.l1_net_smoke
"""
from __future__ import annotations
import os
import time
import requests
from bs4 import BeautifulSoup

from scripts.l1_collect.connectivity_probe import probe_url  # noqa: F401 (链路一致性)
from scripts.l1_collect.step2_scan import _firecrawl_get_html, LIST_MIN_TEXT
from scripts.l1_collect.tavily_client import TavilyClient
from scripts.l1_collect.channel_discovery import NATIONAL_TARGETS, discover_one
from scripts.common.llm import OpenAICompatClient

UA = "Mozilla/5.0 (compatible; ZCE-Probe/0.1)"
HOMES = [
    ("国务院", "https://www.gov.cn/"),
    ("发改委", "https://www.ndrc.gov.cn/"),
    ("能源局", "https://www.nea.gov.cn/"),
    ("工信部", "https://www.miit.gov.cn/"),
    ("财政部", "https://www.mof.gov.cn/"),
]


def hr(t: str) -> None:
    print(f"\n{'=' * 64}\n{t}\n{'=' * 64}")


def main() -> None:
    # 1) BS4 直连(CN路由/反爬实测)
    hr("1) BS4 直连国家级站(CN路由/反爬实测)")
    bs_ok = 0
    for name, url in HOMES:
        t0 = time.time()
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            txt = len(BeautifulSoup(r.text, "html.parser").get_text(strip=True))
            ok = r.status_code < 400 and txt >= LIST_MIN_TEXT
            bs_ok += ok
            print(f"  {'✅' if ok else '❌'} {name:6s} HTTP {r.status_code} "
                  f"text={txt:6d} {time.time() - t0:4.1f}s")
        except Exception as e:
            print(f"  ❌ {name:6s} EXC {type(e).__name__}: {str(e)[:60]}")
    print(f"  → BS4直连成功 {bs_ok}/{len(HOMES)}")

    # 2) firecrawl 渲染(选C命门)
    hr("2) firecrawl 渲染 CN 政府页(选C命门)")
    if not os.environ.get("FIRECRAWL_API_KEY"):
        print("  ❌ FIRECRAWL_API_KEY 未设")
    else:
        t0 = time.time()
        html = _firecrawl_get_html("https://www.gov.cn/")
        print(f"  {'✅' if html else '❌'} firecrawl html_len={len(html)} "
              f"{time.time() - t0:4.1f}s")

    # 3) tavily 搜索(渠道发现)
    hr("3) Tavily 搜索(渠道发现)")
    if not os.environ.get("TAVILY_API_KEY"):
        print("  ❌ TAVILY_API_KEY 未设")
    else:
        t0 = time.time()
        urls = TavilyClient().search_urls("国家发展和改革委员会 政策文件 通知公告 列表", 5)
        print(f"  {'✅' if urls else '❌'} {len(urls)} urls {time.time() - t0:4.1f}s")
        for u in urls:
            print(f"      {u}")

    # 4) deepseek judge 可达(gate)
    hr("4) DeepSeek judge 可达(gate)")
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("  ❌ DEEPSEEK_API_KEY 未设")
    else:
        t0 = time.time()
        try:
            cli = OpenAICompatClient(
                model=os.environ.get("JUDGE_MODEL", "deepseek-v4-flash"),
                base_url="https://api.deepseek.com", api_key=key,
                log_path="state/l1_gate/smoke_calls.jsonl")
            rep = cli.complete("你是助手,只回复用户要的字", "只回复两个字:通了")
            print(f"  ✅ reply={rep!r} {time.time() - t0:4.1f}s")
        except Exception as e:
            print(f"  ❌ EXC {type(e).__name__}: {str(e)[:80]}")

    # 5) 端到端 discover_one(tavily→llm→probe 全链,1个真实国家级目标)
    hr("5) 端到端 discover_one(发改委,验证全链)")
    t0 = time.time()
    ch = discover_one(NATIONAL_TARGETS[0])
    print(f"  status={ch.status.value} probe={ch.probe_result} {time.time() - t0:4.1f}s")
    print(f"  list_url={ch.list_url}")


if __name__ == "__main__":
    main()
