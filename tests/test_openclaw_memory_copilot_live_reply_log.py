from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_openclaw_memory_copilot_live_reply_log import check_live_reply_log


class OpenClawMemoryCopilotLiveReplyLogTest(unittest.TestCase):
    def test_passes_when_card_delivery_ok_after_expected_message(self) -> None:
        report = check_live_reply_log(
            write_log(
                """
                2026-05-02T20:40:00.000+08:00 [feishu] feishu[default]: Feishu[default] message in group oc_demo: /settings
                2026-05-02T20:40:00.100+08:00 [plugins] feishu-memory-copilot route result {"ok":true,"publish":{"mode":"interactive"}}
                2026-05-02T20:40:00.200+08:00 [plugins] feishu-memory-copilot card delivery {"ok":true,"mode":"reply_card"}
                """
            ),
            since="2026-05-02T20:39:00.000+08:00",
        )

        self.assertTrue(report["ok"])
        self.assertEqual("card_delivery_ok", report["status"])

    def test_passes_when_card_delivery_fails_but_visible_fallback_dispatches(self) -> None:
        report = check_live_reply_log(
            write_log(
                """
                2026-05-02T20:40:00.000+08:00 [feishu] feishu[default]: Feishu[default] message in group oc_demo: /settings
                2026-05-02T20:40:00.200+08:00 [plugins] feishu-memory-copilot card delivery {"ok":false,"fallback_reason":"openclaw_gateway_interactive_card_failed"}
                2026-05-02T20:40:00.300+08:00 [feishu] feishu[default]: dispatch complete (queuedFinal=true, replies=1)
                """
            )
        )

        self.assertTrue(report["ok"])
        self.assertEqual("card_delivery_failed_visible_fallback", report["status"])

    def test_passes_when_router_fails_but_visible_fallback_dispatches(self) -> None:
        report = check_live_reply_log(
            write_log(
                """
                2026-05-02T20:40:00.000+08:00 [feishu] feishu[default]: Feishu[default] message in group oc_demo: /settings
                2026-05-02T20:40:00.200+08:00 [plugins] feishu-memory-copilot router failed Error: boom
                2026-05-02T20:40:00.300+08:00 [feishu] feishu[default]: dispatch complete (queuedFinal=true, replies=1)
                """
            )
        )

        self.assertTrue(report["ok"])
        self.assertEqual("router_failed_visible_fallback", report["status"])

    def test_fails_when_expected_message_is_missing_after_since(self) -> None:
        report = check_live_reply_log(
            write_log(
                """
                2026-05-02T20:30:00.000+08:00 [feishu] feishu[default]: Feishu[default] message in group oc_demo: /settings
                """
            ),
            since="2026-05-02T20:39:00.000+08:00",
        )

        self.assertFalse(report["ok"])
        self.assertEqual("expected_message_missing", report["status"])

    def test_fails_when_message_has_no_visible_reply_evidence(self) -> None:
        report = check_live_reply_log(
            write_log(
                """
                2026-05-02T20:40:00.000+08:00 [feishu] feishu[default]: Feishu[default] message in group oc_demo: /settings
                2026-05-02T20:40:00.200+08:00 [plugins] feishu-memory-copilot route result {"ok":true,"publish":{"mode":"interactive"}}
                2026-05-02T20:40:00.300+08:00 [feishu] feishu[default]: dispatch complete (queuedFinal=false, replies=0)
                """
            )
        )

        self.assertFalse(report["ok"])
        self.assertEqual("visible_reply_unproven", report["status"])


def write_log(content: str) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="fmc_live_reply_", suffix=".log", delete=False, mode="w", encoding="utf-8")
    with handle:
        handle.write("\n".join(line.strip() for line in content.strip().splitlines()))
    return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
