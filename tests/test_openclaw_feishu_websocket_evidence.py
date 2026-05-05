from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from scripts.check_openclaw_feishu_websocket import (
    CommandResult,
    redact_text,
    run_openclaw_feishu_websocket_check,
)


def _runner_with(payloads: dict[str, dict]) -> callable:
    def runner(command: Sequence[str], timeout: int) -> CommandResult:
        del timeout
        key = " ".join(command)
        payload = payloads[key]
        return CommandResult(0, json.dumps(payload), "")

    return runner


class OpenClawFeishuWebsocketEvidenceTest(unittest.TestCase):
    def test_passes_with_channel_status_running_and_health_summary_mismatch_warning(self) -> None:
        report = run_openclaw_feishu_websocket_check(
            command_runner=_runner_with(
                {
                    "openclaw channels status --probe --json": {
                        "channels": {
                            "feishu": {
                                "configured": True,
                                "running": True,
                                "probe": {"ok": True},
                                "lastStartAt": 1777359396270,
                            }
                        },
                        "channelAccounts": {
                            "feishu": [
                                {
                                    "enabled": True,
                                    "configured": True,
                                    "running": True,
                                    "probe": {"ok": True},
                                }
                            ]
                        },
                    },
                    "openclaw health --json --timeout 5000": {
                        "ok": True,
                        "channels": {
                            "feishu": {
                                "running": False,
                                "probe": {"ok": True},
                                "accounts": {"default": {"running": False, "probe": {"ok": True}}},
                            }
                        },
                    },
                    "openclaw channels logs --channel feishu --json --lines 120": {
                        "file": "/tmp/openclaw/openclaw-2026-04-28.log",
                        "lines": [
                            {
                                "time": "2026-04-28T14:56:36.274+08:00",
                                "message": "starting feishu[default] (mode: websocket)",
                            },
                            {
                                "time": "2026-04-28T14:56:36.318+08:00",
                                "message": "feishu[default]: WebSocket client started",
                            },
                            {"time": "2026-04-28T14:56:36.666+08:00", "message": "ws client ready"},
                            {
                                "time": "2026-04-28T15:35:02.000+08:00",
                                "message": "received message from ou_xxx in oc_xxx",
                            },
                            {"time": "2026-04-28T15:35:02.010+08:00", "message": "dispatching to agent"},
                            {
                                "time": "2026-04-28T15:35:33.000+08:00",
                                "message": "dispatch complete (queuedFinal=true, replies=1)",
                            },
                        ],
                    },
                }
            ),
            process_rows=["401 1 openclaw-gateway"],
            current_pid=1,
        )

        self.assertTrue(report["ok"])
        self.assertEqual("warning", report["checks"]["health_consistency"]["status"])
        self.assertEqual("pass", report["checks"]["feishu_logs"]["status"])

    def test_fails_when_channel_status_is_not_running(self) -> None:
        report = run_openclaw_feishu_websocket_check(
            command_runner=_runner_with(
                {
                    "openclaw channels status --probe --json": {
                        "channels": {"feishu": {"configured": True, "running": False, "probe": {"ok": True}}},
                        "channelAccounts": {"feishu": [{"enabled": True, "configured": True, "running": False}]},
                    },
                    "openclaw health --json --timeout 5000": {"ok": True, "channels": {"feishu": {"running": False}}},
                    "openclaw channels logs --channel feishu --json --lines 120": {"lines": []},
                }
            ),
            process_rows=[],
            current_pid=1,
        )

        self.assertFalse(report["ok"])
        self.assertEqual("fail", report["checks"]["channels_status"]["status"])

    def test_redacts_feishu_identifiers(self) -> None:
        text = "sender ou_abc chat oc_def message om_ghi app cli_jkl"

        self.assertEqual(
            "sender <redacted_id> chat <redacted_id> message <redacted_id> app <redacted_id>",
            redact_text(text),
        )

    def test_uses_gateway_log_fallback_when_channel_logs_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            gateway_log = Path(temp_dir) / "gateway.log"
            gateway_log.write_text(
                "\n".join(
                    [
                        "2026-05-05T22:00:00+08:00 starting feishu[default] (mode: websocket)",
                        "2026-05-05T22:00:01+08:00 feishu[default]: WebSocket client started",
                        "2026-05-05T22:01:00+08:00 received message from ou_secret in oc_secret",
                        "2026-05-05T22:01:01+08:00 dispatching to agent",
                        "2026-05-05T22:01:02+08:00 dispatch complete (queuedFinal=true, replies=1)",
                    ]
                ),
                encoding="utf-8",
            )
            report = run_openclaw_feishu_websocket_check(
                command_runner=_runner_with(
                    {
                        "openclaw channels status --probe --json": {
                            "channels": {"feishu": {"configured": True, "running": True, "probe": {"ok": True}}},
                            "channelAccounts": {"feishu": [{"enabled": True, "configured": True, "running": True}]},
                        },
                        "openclaw health --json --timeout 5000": {"ok": True, "channels": {"feishu": {"running": True}}},
                        "openclaw channels logs --channel feishu --json --lines 120": {"lines": []},
                    }
                ),
                process_rows=["401 1 openclaw-gateway"],
                current_pid=1,
                gateway_log_path=gateway_log,
            )

        self.assertTrue(report["ok"])
        self.assertEqual("pass", report["checks"]["feishu_logs"]["status"])
        self.assertEqual("available", report["checks"]["feishu_logs"]["gateway_log_fallback"]["status"])


if __name__ == "__main__":
    unittest.main()
