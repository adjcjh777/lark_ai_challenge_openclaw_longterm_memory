from __future__ import annotations

import re

from .models import (
    DECISION_WORDS,
    OVERRIDE_WORDS,
    PREFERENCE_WORDS,
    SUBJECT_RULES,
    WORKFLOW_WORDS,
    ExtractedMemory,
    contains_any,
    normalize_subject,
)


def clean_content(content: str) -> str:
    content = content.strip()
    content = re.sub(r"^@?Memory\s*记住[:：]\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"^/remember\s+", "", content, flags=re.IGNORECASE)
    content = content.strip()
    content = _normalize_override_current_value(content)
    if "JSON" in content and "trace_id" in content and "日志" not in content:
        return f"JSON 格式含 trace_id。{content}"
    return content


def _normalize_override_current_value(content: str) -> str:
    if "最后还是" not in content:
        return content
    if not contains_any(content, ("作废", "收回", "不对")):
        return content
    current = re.split(r"最后还是", content, maxsplit=1)[1].strip(" ，,。.;；")
    if not current:
        return content
    return f"最终：{current}。"


def is_override_intent(content: str) -> bool:
    return contains_any(content, OVERRIDE_WORDS)


def infer_type(content: str) -> str:
    if contains_any(content, WORKFLOW_WORDS):
        return "workflow"
    if contains_any(content, PREFERENCE_WORDS):
        return "preference"
    if contains_any(content, DECISION_WORDS):
        return "decision"
    return "decision"


def infer_subject(text: str) -> str:
    lowered = text.lower()
    for keywords, subject in SUBJECT_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return subject

    fallback = re.split(r"[，。,；;：:\n]", text.strip(), maxsplit=1)[0]
    fallback = fallback.strip()
    return fallback[:24] if fallback else "未分类记忆"


def extract_memory(content: str) -> ExtractedMemory:
    current_value = clean_content(content)
    if not current_value:
        raise ValueError("memory content cannot be empty")

    subject = infer_subject(current_value)
    memory_type = infer_type(current_value)
    confidence = 0.75 if _has_memory_signal(current_value) else 0.55
    importance = 0.8 if memory_type in {"decision", "workflow"} else 0.6

    return ExtractedMemory(
        type=memory_type,
        subject=subject,
        normalized_subject=normalize_subject(subject),
        current_value=current_value,
        reason=_extract_reason(current_value),
        confidence=confidence,
        importance=importance,
    )


def subject_for_query(query: str) -> str:
    return infer_subject(clean_content(query))


def _has_memory_signal(content: str) -> bool:
    return (
        contains_any(content, DECISION_WORDS)
        or contains_any(content, WORKFLOW_WORDS)
        or contains_any(content, PREFERENCE_WORDS)
        or contains_any(content, OVERRIDE_WORDS)
    )


def _extract_reason(content: str) -> str | None:
    for marker in ("原因是", "理由是", "因为"):
        if marker in content:
            return content.split(marker, 1)[1].strip(" 。.，,")
    return None
