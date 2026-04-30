from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_SCOPE = "project:feishu_ai_challenge"

OVERRIDE_WORDS = ("不对", "改成", "以后", "统一", "最终", "从现在起")

DECISION_WORDS = ("决定", "最终", "统一", "以后", "采用", "改成")
WORKFLOW_WORDS = (
    "必须",
    "不允许",
    "不要",
    "部署",
    "发布",
    "流程",
    "命令",
    "负责人",
    "截止",
    "上线窗口",
    "回滚负责人",
)
PREFERENCE_WORDS = ("偏好", "喜欢", "优先")

SUBJECT_RULES = (
    (("部署", "发布", "prod", "生产"), "生产部署"),
    (("周报",), "周报收件人"),
    (("后端", "框架", "fastapi", "nestjs"), "后端框架"),
    (("截止", "deadline", "交付", "周日", "周一"), "截止时间"),
    (("负责人", "owner", "维护"), "负责人"),
    (("数据库", "sqlite", "bitable", "存储"), "数据存储"),
    (("权限", "bot", "机器人", "飞书", "lark"), "飞书接入"),
    (("benchmark", "评测", "测试"), "Benchmark"),
)


@dataclass(frozen=True)
class Scope:
    scope_type: str
    scope_id: str


@dataclass(frozen=True)
class ExtractedMemory:
    type: str
    subject: str
    normalized_subject: str
    current_value: str
    reason: str | None
    confidence: float
    importance: float


def parse_scope(scope: str) -> Scope:
    if ":" not in scope:
        raise ValueError("scope must use '<scope_type>:<scope_id>', for example project:feishu_ai_challenge")
    scope_type, scope_id = scope.split(":", 1)
    scope_type = scope_type.strip()
    scope_id = scope_id.strip()
    if not scope_type or not scope_id:
        raise ValueError("scope_type and scope_id cannot be empty")
    return Scope(scope_type=scope_type, scope_id=scope_id)


def normalize_subject(subject: str) -> str:
    return re.sub(r"\s+", "", subject).strip().lower()


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)
