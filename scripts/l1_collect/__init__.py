"""政策采集 L1:从市级渠道扫描到 vault raw 入库的完整链路。

模块组织:
  - channel_catalog : 渠道清单数据模型 + IO
  - connectivity_probe : HTTP 联通 + 列表页结构启发式
  - city_priority : P0/P1/P2 优先级
  - news_filter : 政策 vs 新闻稿 确定性过滤
  - dedup : 三维查重(URL/文号/标题)
  - fetcher : 抓取兜底链
  - metadata_extractor : 元数据抽取(无 LLM)
  - ingester : 写 vault raw + schema 校验
  - step2_scan / step3_filter / step4_fetch / step4_5_extract / step5_ingest
  - run_pipeline : 总入口
"""
