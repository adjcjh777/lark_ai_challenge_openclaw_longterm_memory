from __future__ import annotations

import unittest

from scripts.check_cross_platform_quick_deploy import parse_openclaw_version, run_preflight


class CrossPlatformQuickDeployTest(unittest.TestCase):
    def test_local_demo_allows_missing_openclaw_as_warning(self) -> None:
        report = run_preflight(
            profile="local-demo",
            sys_platform="darwin",
            python_version=(3, 11, 8),
            command_exists=lambda name: name in {"git", "node", "npm"},
            command_runner=_runner({"pip": "pip 24.0 from /tmp/site-packages/pip (python 3.11)"}),
        )

        self.assertTrue(report["ok"])
        self.assertEqual("macOS", report["platform"])
        openclaw = _check(report, "openclaw_locked_version")
        self.assertEqual("warning", openclaw["status"])
        self.assertIn("not prove production deployment", report["boundary"])

    def test_openclaw_staging_requires_locked_openclaw_and_node(self) -> None:
        report = run_preflight(
            profile="openclaw-staging",
            sys_platform="linux",
            python_version=(3, 11, 8),
            command_exists=lambda name: name == "git",
            command_runner=_runner({"pip": "pip 24.0"}),
        )

        self.assertFalse(report["ok"])
        self.assertEqual("Linux", report["platform"])
        self.assertEqual("fail", _check(report, "openclaw_locked_version")["status"])
        self.assertEqual("fail", _check(report, "node_npm")["status"])

    def test_windows_commands_are_powershell_native(self) -> None:
        report = run_preflight(
            profile="openclaw-staging",
            sys_platform="win32",
            python_version=(3, 11, 8),
            command_exists=lambda name: name in {"git", "node", "npm", "openclaw"},
            command_runner=_runner(
                {
                    "pip": "pip 24.0",
                    "openclaw": "OpenClaw 2026.4.24",
                }
            ),
        )

        self.assertTrue(report["ok"])
        setup_commands = "\n".join(report["next_commands"]["setup_repo"])
        self.assertIn("py -3.11 -m venv .venv", setup_commands)
        self.assertIn(".\\.venv\\Scripts\\Activate.ps1", setup_commands)

    def test_python_39_is_warning_but_not_blocking(self) -> None:
        report = run_preflight(
            profile="local-demo",
            sys_platform="darwin",
            python_version=(3, 9, 18),
            command_exists=lambda name: name in {"git"},
            command_runner=_runner({"pip": "pip 24.0"}),
        )

        self.assertTrue(report["ok"])
        self.assertEqual("warning", _check(report, "python_version")["status"])

    def test_old_openclaw_version_fails_when_cli_present(self) -> None:
        report = run_preflight(
            profile="local-demo",
            sys_platform="darwin",
            python_version=(3, 11, 8),
            command_exists=lambda name: name in {"git", "node", "npm", "openclaw"},
            command_runner=_runner({"pip": "pip 24.0", "openclaw": "OpenClaw 2026.4.23"}),
        )

        self.assertFalse(report["ok"])
        self.assertEqual("fail", _check(report, "openclaw_locked_version")["status"])

    def test_embedding_profile_requires_default_ollama_model(self) -> None:
        report = run_preflight(
            profile="embedding",
            sys_platform="darwin",
            python_version=(3, 11, 8),
            command_exists=lambda name: name in {"git", "node", "npm", "openclaw", "ollama"},
            command_runner=_runner({"pip": "pip 24.0", "openclaw": "OpenClaw 2026.4.24", "ollama_list": "NAME ID"}),
        )

        self.assertFalse(report["ok"])
        self.assertEqual("fail", _check(report, "ollama")["status"])

    def test_parse_openclaw_version(self) -> None:
        self.assertEqual("2026.4.24", parse_openclaw_version("OpenClaw 2026.4.24"))
        self.assertIsNone(parse_openclaw_version("unexpected"))


def _check(report: dict, name: str) -> dict:
    return next(check for check in report["checks"] if check["name"] == name)


def _runner(outputs: dict[str, str]):
    def run(command: list[str]) -> dict:
        if command[:3] == ["python", "-m", "pip"] or command[-2:] == ["pip", "--version"] or "pip" in command:
            return {"returncode": 0, "stdout": outputs.get("pip", "pip 24.0"), "stderr": ""}
        if command[:2] == ["openclaw", "--version"]:
            stdout = outputs.get("openclaw")
            if stdout is None:
                return {"returncode": 1, "stdout": "", "stderr": "openclaw missing"}
            return {"returncode": 0, "stdout": stdout, "stderr": ""}
        if command[:2] == ["ollama", "list"]:
            return {"returncode": 0, "stdout": outputs.get("ollama_list", ""), "stderr": ""}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    return run


if __name__ == "__main__":
    unittest.main()
