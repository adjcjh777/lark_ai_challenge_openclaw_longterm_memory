from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_SCOPE = "project:feishu_ai_challenge"

OVERRIDE_WORDS = (
    "不对",
    "改成",
    "以后",
    "统一",
    "最终",
    "从现在起",
    "换成",
    "切 ",
    "切回",
    "还是回",
    "还是得",
    "提高到",
    "调到",
    "要加",
    "加上",
    "砍掉",
    "不用",
    "不再",
    "已迁移",
    "迁移",
    "已变更",
    "变更",
)

DECISION_WORDS = ("决定", "最终", "统一", "以后", "采用", "改成", "调成", "调整到", "升级到")
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
    "规范",
)
PREFERENCE_WORDS = ("偏好", "喜欢", "优先")

SUBJECT_RULES = (
    (("容器编排", "docker compose", "kubernetes", "k8s"), "容器编排"),
    (("发布策略", "release strategy", "blue-green deployment"), "发布策略"),
    (("ci 并行", "并行度"), "CI 并行度"),
    (("api 接口", "endpoint", "https://api.internal"), "API 接口"),
    (("api 超时", "超时时间", "网关超时"), "API 超时"),
    (("缓存策略", "redis", "memcached"), "缓存策略"),
    (("备份保留", "保留期", "存储桶"), "备份策略"),
    (("日志格式", "trace_id", "纯文本"), "日志格式"),
    (("覆盖率", "无意义 mock"), "测试覆盖率"),
    (("代码评审", "peer review", "formal review", "approve"), "代码评审"),
    (("看板列", "blocked", "in review", "doing", "done", "列太多"), "看板列"),
    (("周报",), "周报收件人"),
    (("前端", "vue", "react", "组件库", "element plus"), "前端框架"),
    (("部署", "发布", "prod", "生产", "deployment"), "生产部署"),
    (("后端", "框架", "fastapi", "nestjs"), "后端框架"),
    (("截止", "deadline", "交付", "周日", "周一"), "截止时间"),
    (("负责人", "owner", "维护"), "负责人"),
    (("分支命名", "feature/", "feat/", "bugfix/", "hotfix/"), "分支命名"),
    (("团队通知", "通知渠道", "bot-notify"), "团队通知渠道"),
    (("数据库", "sqlite", "bitable", "存储", "mysql", "postgresql"), "数据存储"),
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
