from dataclasses import dataclass, field


@dataclass
class PolicyRecord:
    pid: str                 # frontmatter id
    path: str                # 绝对路径
    title: str
    official_number: str
    date: str                # "YYYY-MM-DD" 或 ""
    issuer: list             # 统一为 list[str]（单值也包成 list）
    issuer_canonical: list   # 统一为 list[str]
    url: str
    body_head: str           # 正文前 2000 字符（喂 LLM 用）
    raw_fm: dict             # 原始 frontmatter dict


@dataclass
class Finding:
    check: str               # "news_release" | "id_issuer" | "dedup" | "p1900"
    pid: str
    detail: dict = field(default_factory=dict)
    proposed_action: str = ""   # 人类可读的提议（dry-run 只写不执行）
