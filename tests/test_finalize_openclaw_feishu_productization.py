from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.finalize_openclaw_feishu_productization import finalize_openclaw_feishu_productization


class FinalizeOpenClawFeishuProductizationTest(unittest.TestCase):
    def test_writes_audit_and_keeps_blockers_when_live_permission_and_cognee_are_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_feishu_finalizer_") as temp_dir:
            root = Path(temp_dir)
            openclaw_log = _write_jsonl(root / "openclaw.ndjson", [_passive_message(), _candidate_result()])
            routing_log = _write_jsonl(
                root / "routing.ndjson",
                [_routing_result(tool) for tool in ("fmc_memory_search", "fmc_memory_create_candidate", "fmc_memory_prefetch")],
            )
            cognee_dir = root / "cognee"
            cognee_dir.mkdir()
            _write_json(cognee_dir / "curated-sync-report.json", _curated_sync_report())
            _write_json(cognee_dir / "persistent-readback-report.json", _readback_report())
            _write_samples(
                cognee_dir / "embedding-samples.ndjson",
                [
                    _embedding_sample("2026-05-01T00:00:00+00:00"),
                    _embedding_sample("2026-05-01T12:00:00+00:00"),
                ],
            )
            (cognee_dir / "sampler.pid").write_text(str(os.getpid()), encoding="utf-8")

            result = finalize_openclaw_feishu_productization(
                openclaw_log=openclaw_log,
                routing_event_log=routing_log,
                feishu_event_diagnostics=None,
                cognee_dir=cognee_dir,
                output_dir=root / "out",
            )

            self.assertFalse(result["goal_complete"])
            self.assertTrue(Path(result["audit_path"]).exists())
            blockers = {item["name"]: item["reason"] for item in result["blockers"]}
            self.assertEqual("non_reviewer_enable_memory_denial_missing", blockers["live_negative_permission_second_user"])
            self.assertEqual(
                "cognee_sampler_running_but_window_incomplete",
                blockers["cognee_embedding_long_term_service"],
            )


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, payloads: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads), encoding="utf-8")
    return path


def _write_samples(path: Path, samples: list[dict[str, object]]) -> Path:
    return _write_jsonl(path, samples)


def _passive_message() -> dict[str, object]:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user"}, "sender_type": "user"},
            "message": {
                "message_id": "om_passive",
                "chat_id": "oc_group",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "决定：非 @ 群消息 live gate 测试。"}, ensure_ascii=False),
                "create_time": "1777647600000",
            },
        },
    }


def _candidate_result() -> dict[str, object]:
    return {
        "result": {
            "ok": True,
            "message_id": "om_candidate",
            "tool": "memory.create_candidate",
            "publish": {
                "mode": "reply_card",
                "card": {
                    "elements": [
                        {
                            "tag": "action",
                            "actions": [
                                {
                                    "text": {"tag": "plain_text", "content": "确认保存"},
                                    "value": {"memory_engine_action": "confirm"},
                                }
                            ],
                        }
                    ]
                },
            },
        }
    }


def _routing_result(tool: str) -> dict[str, object]:
    return {
        "result": {
            "ok": True,
            "tool_result": {
                "ok": True,
                "bridge": {
                    "entrypoint": "openclaw_tool",
                    "tool": tool,
                    "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
                },
            },
        }
    }


def _curated_sync_report() -> dict[str, object]:
    return {
        "ok": True,
        "dataset_name": "copilot_project_feishu_ai_challenge",
        "memory_id": "mem_cognee",
        "cognee_sync": {"status": "pass", "fallback": None},
    }


def _readback_report() -> dict[str, object]:
    return {
        "ok": True,
        "matched_memory": True,
        "checks": {"store_reopened": {"status": "pass"}, "reopened_search_ok": {"status": "pass"}},
    }


def _embedding_sample(sampled_at: str) -> dict[str, object]:
    return {
        "ok": True,
        "status": "ready",
        "sampled_at": sampled_at,
        "expected_dimensions": 1024,
        "actual_dimensions": 1024,
    }


if __name__ == "__main__":
    unittest.main()
