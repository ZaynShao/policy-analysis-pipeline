from dataclasses import dataclass, field, asdict

@dataclass
class Scores:
    D1: int; D2: int; D3: int; D4: int; D5: int; D6: int
    def to_dict(self): return {k: getattr(self, k) for k in ("D1","D2","D3","D4","D5","D6")}
    @classmethod
    def from_dict(cls, d): return cls(**{k: int(d[k]) for k in ("D1","D2","D3","D4","D5","D6")})

@dataclass
class BusinessViewDraft:
    pid: str
    themes: list
    primary_theme: str
    scores: Scores
    importance: int = None
    action_class: str = None
    value_tags: list = field(default_factory=list)
    gate_passed_deep: bool = False
    comprehensive: bool = False   # 综合/纲领政策:跨多主题无单一中心,primary 为名义主书架
    影响分析: dict = None
    行动建议: list = field(default_factory=list)
    didi_impact_one_liner: str = None

@dataclass
class JudgeVerdict:
    verdict: str
    dim: str
    reason: str
    confidence: float

@dataclass
class QueueRecord:
    pid: str
    stage: str
    reason: str
    detail: dict = field(default_factory=dict)
    def to_dict(self): return asdict(self)

@dataclass
class GoldenRecord:
    pid: str
    gold_themes: list
    gold_primary: str
    gold_scores: dict
    gold_影响分析: dict = None
    is_planted: bool = False
    error_type: str = None
