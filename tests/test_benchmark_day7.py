from __future__ import annotations

import csv
import unittest
import uuid
from pathlib import Path

from memory_engine.benchmark import run_benchmark, write_benchmark_outputs


class Day7BenchmarkTest(unittest.TestCase):
    def test_anti_interference_metrics_cover_three_layers(self) -> None:
        result = run_benchmark("benchmarks/day7_anti_interference.json")
        summary = result["summary"]

        self.assertEqual("anti_interference", result["benchmark_type"])
        self.assertEqual(1050, result["layers"]["raw_events"])
        self.assertEqual(50, result["layers"]["curated_memories"])
        self.assertEqual(50, result["layers"]["recall_logs"])
        self.assertEqual(1.0, summary["recall_at_1"])
        self.assertEqual(1.0, summary["recall_at_3"])
        self.assertEqual(1.0, summary["mrr"])
        self.assertIn("workflow", result["by_type"])
        self.assertIn("D7记忆001", result["by_subject"])

    def test_anti_interference_outputs_markdown_and_csv(self) -> None:
        result = run_benchmark("benchmarks/day7_anti_interference.json")
        tmp_path = Path("data") / ".test_day7_outputs"
        tmp_path.mkdir(parents=True, exist_ok=True)
        suffix = uuid.uuid4().hex
        markdown_path = tmp_path / f"benchmark-report-{suffix}.md"
        csv_path = tmp_path / f"day7-{suffix}.csv"

        try:
            write_benchmark_outputs(result, markdown_output=markdown_path, csv_output=csv_path)

            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("D7 抗干扰召回评测", markdown)
            self.assertIn("raw events", markdown)
            self.assertIn("Recall@1", markdown)

            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(50, len(rows))
            self.assertEqual("d7_query_001", rows[0]["query_id"])
        finally:
            markdown_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
