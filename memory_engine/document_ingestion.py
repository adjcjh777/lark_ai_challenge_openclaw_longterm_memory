from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import DECISION_WORDS, DEFAULT_SCOPE, OVERRIDE_WORDS, PREFERENCE_WORDS, WORKFLOW_WORDS, contains_any
from .repository import MemoryRepository


@dataclass(frozen=True)
class DocumentSource:
    token: str
    title: str
    text: str
    source_type: str


def ingest_document_source(
    repo: MemoryRepository,
    url_or_token: str,
    *,
    scope: str = DEFAULT_SCOPE,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    document = load_document_source(
        url_or_token,
        lark_cli=lark_cli,
        profile=profile,
        as_identity=as_identity,
    )
    candidates = extract_candidate_quotes(document.text, limit=limit)
    results = []
    for index, quote in enumerate(candidates, start=1):
        source_id = f"{document.token}#candidate-{index}"
        results.append(
            repo.add_candidate(
                scope,
                quote,
                source_type=document.source_type,
                source_id=source_id,
                document_token=document.token,
                document_title=document.title,
                quote=quote,
            )
        )

    created = [result for result in results if result.get("action") == "created"]
    duplicates = [result for result in results if result.get("action") == "duplicate"]
    return {
        "ok": True,
        "document": {
            "token": document.token,
            "title": document.title,
            "source_type": document.source_type,
        },
        "candidate_count": len(created),
        "duplicate_count": len(duplicates),
        "candidates": results,
    }


def load_document_source(
    url_or_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> DocumentSource:
    path = Path(url_or_token).expanduser()
    if path.exists():
        text = path.read_text(encoding="utf-8")
        return DocumentSource(
            token=str(path.resolve()),
            title=_title_from_markdown(text, path),
            text=text,
            source_type="document_markdown",
        )

    token = document_token_from_url(url_or_token)
    text = fetch_feishu_document_text(token, lark_cli=lark_cli, profile=profile, as_identity=as_identity)
    return DocumentSource(
        token=token,
        title=_title_from_text(text, fallback=token),
        text=text,
        source_type="document_feishu",
    )


def fetch_feishu_document_text(
    token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> str:
    command = [lark_cli]
    if profile:
        command.extend(["--profile", profile])
    if as_identity:
        command.extend(["--as", as_identity])
    command.extend(["docs", "+fetch", token])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout


def document_token_from_url(url_or_token: str) -> str:
    stripped = url_or_token.strip()
    for pattern in (
        r"/docx/([A-Za-z0-9]+)",
        r"/docs/([A-Za-z0-9]+)",
        r"[?&]token=([A-Za-z0-9]+)",
    ):
        match = re.search(pattern, stripped)
        if match:
            return match.group(1)
    return stripped


def extract_candidate_quotes(text: str, *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for block in _iter_candidate_blocks(text):
        normalized = re.sub(r"\s+", " ", block).strip()
        if not normalized or normalized in seen:
            continue
        if _has_candidate_signal(normalized):
            seen.add(normalized)
            candidates.append(normalized)
        if len(candidates) >= limit:
            break
    return candidates


def _iter_candidate_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for line in text.splitlines():
        line = _clean_markdown_line(line)
        if not line:
            continue
        if len(line) <= 240:
            blocks.append(line)
            continue
        blocks.extend(part.strip() for part in re.split(r"[。；;]", line) if part.strip())
    return blocks


def _clean_markdown_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s+", "", line)
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.)、]\s+", "", line)
    line = re.sub(r"^>\s*", "", line)
    return line.strip()


def _has_candidate_signal(text: str) -> bool:
    signal_words = DECISION_WORDS + WORKFLOW_WORDS + PREFERENCE_WORDS + OVERRIDE_WORDS
    if contains_any(text, signal_words):
        return True
    return bool(re.match(r"^(记忆|规则|结论|约束|风险|负责人)[:：]", text))


def _title_from_markdown(text: str, path: Path) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip() or path.stem
    return path.stem


def _title_from_text(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        line = _clean_markdown_line(line)
        if line:
            return line[:80]
    return fallback
