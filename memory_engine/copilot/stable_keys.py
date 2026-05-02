from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from memory_engine.models import normalize_subject, parse_scope


@dataclass(frozen=True)
class StableKeyResolution:
    stable_key: str
    slot_type: str
    slot_name: str
    project_slug: str
    aliases: list[str]
    confidence: float
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_DEPLOY_REGION_MARKERS = ("region", "cn-shanghai", "ap-shanghai", "机房", "区域")
_DEPLOY_STRATEGY_MARKERS = ("--canary", "--blue-green", "canary", "blue-green", "灰度")
_DEADLINE_MARKERS = ("截止", "deadline", "提交", "周日", "周一", "中午", "晚上")
_OWNER_MARKERS = ("负责人", "owner", "维护", "owner是")
_WEEKLY_REPORT_MARKERS = ("周报",)
_WEEKLY_REPORT_TARGET_MARKERS = ("发到", "收件", "接收", "任务群", "项目群")
_BITABLE_WRITE_MARKERS = ("bitable", "多维表格", "base record", "sheets", "写入", "写回", "看板")
_FEISHU_REVIEW_SUBJECT_MARKERS = ("飞书", "bot", "机器人", "copilot service")
_FEISHU_REVIEW_ACTION_MARKERS = ("候选", "确认", "权限")
_BENCHMARK_REPORT_MARKERS = ("benchmark", "评测", "报告", "recall", "evidence coverage")
_DEMO_FLOW_MARKERS = ("demo", "演示", "录屏", "展示")


def resolve_stable_memory_key(
    text: str,
    *,
    scope: str,
    subject: str | None = None,
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
) -> StableKeyResolution:
    """Resolve semantically equivalent memory updates to a deterministic slot key."""

    cleaned = _compact_text(text)
    lowered = cleaned.lower()
    parsed_scope = parse_scope(scope)
    project_slug = _project_slug(cleaned, parsed_scope.scope_id, subject)

    slot_type, slot_name, aliases, confidence, explanation = _slot(cleaned, lowered, subject)
    stable_key = "/".join(
        [
            _safe_slug(tenant_id),
            _safe_slug(organization_id),
            _safe_slug(f"{parsed_scope.scope_type}:{parsed_scope.scope_id}"),
            project_slug,
            slot_type,
            slot_name,
        ]
    )
    return StableKeyResolution(
        stable_key=stable_key,
        slot_type=slot_type,
        slot_name=slot_name,
        project_slug=project_slug,
        aliases=aliases,
        confidence=confidence,
        explanation=explanation,
    )


def _slot(text: str, lowered: str, subject: str | None) -> tuple[str, str, list[str], float, str]:
    subject_norm = normalize_subject(subject or "")
    if _contains_any(lowered, _DEPLOY_REGION_MARKERS):
        return (
            "deploy_region",
            "production_deploy_region",
            ["生产部署 region", "部署机房", "release region"],
            0.92,
            "部署地域/机房更新归为同一个生产部署 region slot。",
        )
    if _contains_any(lowered, _DEPLOY_STRATEGY_MARKERS):
        return (
            "deploy_strategy",
            "production_deploy_strategy",
            ["生产部署参数", "发布策略", "canary", "blue-green"],
            0.86,
            "部署参数和灰度策略归为同一个发布策略 slot。",
        )
    if _contains_any(lowered, ("openclaw",)) and "版本" in text:
        return (
            "tool_version",
            "openclaw_version",
            ["OpenClaw 版本", "OpenClaw 固定版本"],
            0.9,
            "OpenClaw 固定版本更新归为工具版本 slot。",
        )
    if _contains_any(lowered, _WEEKLY_REPORT_MARKERS) and _contains_any(lowered, _WEEKLY_REPORT_TARGET_MARKERS):
        return (
            "weekly_report_recipient",
            "weekly_report_recipient",
            ["周报收件人", "周报发送群", "周报接收人"],
            0.9,
            "周报发送目标归为周报收件人 slot。",
        )
    if _contains_any(lowered, _OWNER_MARKERS):
        return (
            "owner",
            _owner_slot_name(text, subject_norm),
            ["负责人", "owner", "维护人"],
            0.84,
            "负责人/维护人表达归为 owner slot。",
        )
    if _contains_any(lowered, _DEADLINE_MARKERS):
        return (
            "deadline",
            _deadline_slot_name(text, subject_norm),
            ["截止时间", "提交时间", "deadline"],
            0.86,
            "提交、截止和相对日期表达归为 deadline slot。",
        )
    if _contains_any(lowered, _BENCHMARK_REPORT_MARKERS):
        return (
            "benchmark_reporting",
            "benchmark_report_metrics",
            ["Benchmark 报告指标", "评测报告口径"],
            0.84,
            "Benchmark 报告指标口径归为同一个报告 slot。",
        )
    if "覆盖率" in text:
        return (
            "coverage_standard",
            "test_coverage_standard",
            ["测试覆盖率标准"],
            0.84,
            "测试覆盖率标准归为 coverage slot。",
        )
    if _contains_any(lowered, _BITABLE_WRITE_MARKERS):
        return (
            "bitable_write_path",
            "bitable_write_path",
            ["Bitable 写入链路", "Base record", "Sheets API"],
            0.84,
            "Bitable 看板写入/写回链路归为同一个工具路径 slot。",
        )
    if "日志保留" in text:
        return ("retention_policy", "log_retention_days", ["日志保留天数"], 0.84, "日志保留天数归为 retention slot。")
    if "备份" in text and ("保留" in text or "保留期" in text):
        return ("retention_policy", "backup_retention_days", ["备份保留期"], 0.84, "备份保留期归为 retention slot。")
    if "日志" in text and ("级别" in text or "输出" in text or "info" in lowered or "warn" in lowered):
        return (
            "log_level",
            "production_log_level",
            ["生产日志级别", "日志输出级别"],
            0.84,
            "日志级别归为 logging slot。",
        )
    if ("rpc" in lowered or "远程调用" in text) and "重试" in text:
        return (
            "retry_count",
            "rpc_retry_count",
            ["RPC 重试次数", "远程调用重试次数"],
            0.84,
            "RPC/远程调用重试次数归为 retry slot。",
        )
    if "音频" in text and ("编码" in text or "压缩格式" in text):
        return ("codec", "audio_codec", ["音频编码格式", "音频压缩格式"], 0.84, "音频编码/压缩格式归为 codec slot。")
    if ("分块" in text or "切分" in text) and ("token" in lowered or "粒度" in text or "大小" in text):
        return (
            "chunk_size",
            "document_chunk_size",
            ["文档分块大小", "文本切分粒度"],
            0.84,
            "文档分块/文本切分粒度归为 chunk size slot。",
        )
    if ("api" in lowered or "网关" in text) and "超时" in text:
        return (
            "timeout",
            "api_gateway_timeout",
            ["API 超时时间", "网关超时"],
            0.84,
            "API/网关超时配置归为 timeout slot。",
        )
    if "缓存策略" in text or "redis" in lowered or "memcached" in lowered:
        return ("cache_strategy", "cache_strategy", ["缓存策略"], 0.84, "缓存策略归为 cache slot。")
    if "连接池" in text:
        if "应用连接池" in text:
            return (
                "app_pool_size",
                "application_pool_size",
                ["应用连接池大小"],
                0.84,
                "应用连接池大小归为 app pool slot。",
            )
        return ("db_pool_size", "database_pool_size", ["数据库连接池大小"], 0.82, "连接池大小归为 database pool slot。")
    if "mysql" in lowered and "版本" in text:
        return ("database_version", "mysql_version", ["MySQL 版本"], 0.84, "MySQL 版本归为 database version slot。")
    if "端口" in text:
        return ("service_port", "service_port", ["服务端口"], 0.84, "服务端口归为 port slot。")
    if "cron" in lowered or ("数据同步" in text and ("小时" in text or "频率" in text)):
        return (
            "schedule",
            "data_sync_schedule",
            ["数据同步频率", "数据同步 cron"],
            0.84,
            "数据同步 cron/频率归为 schedule slot。",
        )
    if _contains_any(lowered, _FEISHU_REVIEW_SUBJECT_MARKERS) and _contains_any(lowered, _FEISHU_REVIEW_ACTION_MARKERS):
        return (
            "feishu_review_policy",
            "feishu_candidate_confirmation_policy",
            ["飞书 Bot 确认边界", "候选记忆确认策略"],
            0.82,
            "飞书 Bot 和 Copilot service 的确认边界归为 review policy slot。",
        )
    if _contains_any(lowered, _DEMO_FLOW_MARKERS):
        return (
            "demo_flow",
            "demo_recording_flow",
            ["Demo 录屏流程", "演示顺序"],
            0.82,
            "Demo/录屏展示顺序归为同一个流程 slot。",
        )
    if "ci" in lowered and "并行" in text:
        return ("ci_parallelism", "ci_parallelism", ["CI 并行度"], 0.82, "CI 并行度归为 execution slot。")

    fallback_subject = subject_norm or normalize_subject(text[:24]) or "uncategorized"
    return (
        "subject",
        _safe_slug(fallback_subject),
        [subject or fallback_subject],
        0.55,
        "未命中特定 slot 规则，降级为 subject-level key。",
    )


def _project_slug(text: str, scope_id: str, subject: str | None) -> str:
    lowered = text.lower()
    if "openclaw" in lowered:
        return "openclaw"
    if "bitable" in lowered or "多维表格" in text:
        return "bitable"
    if "飞书" in text or "lark" in lowered:
        return "feishu"
    if "benchmark" in lowered or "评测" in text:
        return "benchmark"
    if "demo" in lowered or "演示" in text or "录屏" in text:
        return "demo"
    if subject and ("部署" in subject or "生产" in subject):
        return "production_deploy"
    return _safe_slug(scope_id)


def _owner_slot_name(text: str, subject_norm: str) -> str:
    if "openclaw" in text.lower() and "产品化" in text:
        return "openclaw_productization_owner"
    if "生产部署" in text or "发布窗口" in text:
        return "production_deploy_owner"
    return _safe_slug(subject_norm or "owner")


def _deadline_slot_name(text: str, subject_norm: str) -> str:
    if "初赛" in text or "材料" in text:
        return "preliminary_material_deadline"
    return _safe_slug(subject_norm or "deadline")


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _safe_slug(value: str) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^0-9a-zA-Z_\-:\u4e00-\u9fff]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "unknown"
