#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_engine.copilot.admin import create_admin_server
from memory_engine.copilot.knowledge_site import export_knowledge_site
from memory_engine.db import connect, init_db
from scripts.demo_seed import DEFAULT_SCOPE, seed_demo_memories

PLAYWRIGHT_VERSION = "1.59.1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run browser smoke checks for the Copilot Admin Graph UI and static LLM Wiki site."
    )
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to a temporary seeded DB.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Scope to export for the static knowledge site.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for screenshots and static export. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-output", action="store_true", help="Keep temporary output when --output-dir is omitted."
    )
    parser.add_argument(
        "--visual-baseline-dir",
        default=None,
        help=(
            "Optional directory containing baseline PNG screenshots. "
            "When set, the smoke compares current screenshots with baseline images."
        ),
    )
    parser.add_argument(
        "--update-visual-baseline",
        action="store_true",
        help="Write current screenshots and metrics to --visual-baseline-dir instead of comparing.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()
    if args.update_visual_baseline and not args.visual_baseline_dir:
        parser.error("--update-visual-baseline requires --visual-baseline-dir")

    with _workspace(
        db_path=args.db_path,
        output_dir=args.output_dir,
        keep_output=args.keep_output,
        scope=args.scope,
    ) as workspace:
        report = run_ui_smoke(
            db_path=workspace["db_path"],
            output_dir=workspace["output_dir"],
            scope=args.scope,
            visual_baseline_dir=Path(args.visual_baseline_dir).expanduser() if args.visual_baseline_dir else None,
            update_visual_baseline=args.update_visual_baseline,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(format_report(report))
        return 0 if report["ok"] else 1


def run_ui_smoke(
    *,
    db_path: Path,
    output_dir: Path,
    scope: str,
    visual_baseline_dir: Path | None = None,
    update_visual_baseline: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    static_dir = output_dir / "static-site"
    export_result = export_knowledge_site(db_path=db_path, output_dir=static_dir, scope=scope)

    server = create_admin_server("127.0.0.1", 0, db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = {
            "adminUrl": f"http://127.0.0.1:{server.server_port}/",
            "staticUrl": (Path(export_result["entrypoint"]).resolve()).as_uri(),
            "outputDir": str(output_dir.resolve()),
            "visualBaselineDir": str(visual_baseline_dir.resolve()) if visual_baseline_dir else None,
            "updateVisualBaseline": update_visual_baseline,
        }
        node_result = _run_playwright_smoke(config=config, work_dir=output_dir)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return {
        "ok": bool(node_result.get("ok")),
        "boundary": "UI smoke only; no production deployment or productized live claim.",
        "db_path": str(db_path),
        "output_dir": str(output_dir),
        "static_entrypoint": export_result["entrypoint"],
        "checks": node_result.get("checks", {}),
        "screenshots": node_result.get("screenshots", {}),
        "visual_metrics": node_result.get("visual_metrics", {}),
        "visual_diffs": node_result.get("visual_diffs", {}),
        "visual_baseline_dir": str(visual_baseline_dir.resolve()) if visual_baseline_dir else None,
        "visual_baseline_mode": "update"
        if update_visual_baseline
        else ("compare" if visual_baseline_dir else "integrity"),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Copilot Admin / Static Knowledge Site UI Smoke",
        f"ok: {str(report['ok']).lower()}",
        f"boundary: {report['boundary']}",
        f"output_dir: {report['output_dir']}",
        "",
        "checks:",
    ]
    for name, check in sorted(report.get("checks", {}).items()):
        lines.append(f"- {name}: {check.get('status')} {check.get('message', '')}".rstrip())
    return "\n".join(lines)


def _run_playwright_smoke(*, config: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    node_dir = work_dir / "node-playwright"
    node_dir.mkdir(parents=True, exist_ok=True)
    script_path = node_dir / "copilot_ui_smoke.js"
    config_path = node_dir / "config.json"
    script_path.write_text(_NODE_SMOKE_SCRIPT, encoding="utf-8")
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    _ensure_playwright(node_dir)
    result = subprocess.run(
        ["node", str(script_path), str(config_path)],
        cwd=node_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "checks": {
                "playwright": {
                    "status": "fail",
                    "message": (result.stderr or result.stdout).strip(),
                }
            },
            "screenshots": {},
        }
    return json.loads(result.stdout)


def _ensure_playwright(node_dir: Path) -> None:
    probe = subprocess.run(
        ["node", "-e", "require.resolve('playwright')"],
        cwd=node_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        return
    if not shutil.which("npm"):
        raise RuntimeError("npm is required to install the temporary Playwright smoke dependency.")
    subprocess.run(
        [
            "npm",
            "install",
            "--silent",
            "--no-audit",
            "--no-fund",
            f"playwright@{PLAYWRIGHT_VERSION}",
        ],
        cwd=node_dir,
        check=True,
    )


class _workspace:
    def __init__(self, *, db_path: str | None, output_dir: str | None, keep_output: bool, scope: str):
        self.explicit_db_path = Path(db_path).expanduser() if db_path else None
        self.explicit_output_dir = Path(output_dir).expanduser() if output_dir else None
        self.keep_output = keep_output
        self.scope = scope
        self.tmp: tempfile.TemporaryDirectory[str] | None = None
        self.kept_tmp_path: Path | None = None
        self.created_db = False

    def __enter__(self) -> dict[str, Path]:
        if self.explicit_output_dir:
            output_dir = self.explicit_output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
        elif self.keep_output:
            output_dir = Path(tempfile.mkdtemp(prefix="copilot_ui_smoke_"))
            self.kept_tmp_path = output_dir
        else:
            self.tmp = tempfile.TemporaryDirectory(prefix="copilot_ui_smoke_")
            output_dir = Path(self.tmp.name)
        db_path = self.explicit_db_path or output_dir / "copilot-ui-smoke.sqlite"
        if not db_path.exists():
            self.created_db = True
            conn = connect(db_path)
            try:
                init_db(conn)
                seed_demo_memories(conn, self.scope)
            finally:
                conn.close()
        return {"db_path": db_path, "output_dir": output_dir}

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.kept_tmp_path is not None:
            print(f"Kept UI smoke output: {self.kept_tmp_path}", file=sys.stderr)
        if self.tmp is not None:
            self.tmp.cleanup()


_NODE_SMOKE_SCRIPT = r"""
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { chromium } = require("playwright");

const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const screenshots = {};
const checks = {};
const visual_metrics = {};
const visual_diffs = {};
const VISUAL_BASELINE_MANIFEST = "visual-baseline.json";
const VISUAL_BASELINE = {
  minFileBytes: 8000,
  minUniqueColors: 32,
  minInkRatio: 0.015,
  maxDominantColorRatio: 0.985,
  sampleStride: 6,
  diffSampleStride: 8,
  maxPixelDiffRatio: 0.035,
  maxMeanPixelDelta: 8,
  significantPixelDelta: 30,
};

function pass(name, message) {
  checks[name] = { status: "pass", message };
}

function fail(name, message) {
  checks[name] = { status: "fail", message };
}

function readUInt32(buffer, offset) {
  return buffer.readUInt32BE(offset);
}

function paethPredictor(left, up, upperLeft) {
  const p = left + up - upperLeft;
  const pa = Math.abs(p - left);
  const pb = Math.abs(p - up);
  const pc = Math.abs(p - upperLeft);
  if (pa <= pb && pa <= pc) return left;
  if (pb <= pc) return up;
  return upperLeft;
}

function decodePng(filePath) {
  const buffer = fs.readFileSync(filePath);
  const signature = buffer.slice(0, 8).toString("hex");
  if (signature !== "89504e470d0a1a0a") {
    throw new Error(`${path.basename(filePath)} is not a PNG screenshot`);
  }
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idatChunks = [];
  while (offset < buffer.length) {
    const length = readUInt32(buffer, offset);
    const type = buffer.slice(offset + 4, offset + 8).toString("ascii");
    const data = buffer.slice(offset + 8, offset + 8 + length);
    offset += length + 12;
    if (type === "IHDR") {
      width = readUInt32(data, 0);
      height = readUInt32(data, 4);
      bitDepth = data[8];
      colorType = data[9];
      const interlace = data[12];
      if (bitDepth !== 8 || interlace !== 0 || ![2, 6].includes(colorType)) {
        throw new Error(`${path.basename(filePath)} uses unsupported PNG format`);
      }
    } else if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type === "IEND") {
      break;
    }
  }
  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const inflated = zlib.inflateSync(Buffer.concat(idatChunks));
  const pixels = Buffer.alloc(width * height * channels);
  let inputOffset = 0;
  let outputOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = inflated[inputOffset];
    inputOffset += 1;
    for (let x = 0; x < stride; x += 1) {
      const raw = inflated[inputOffset + x];
      const left = x >= channels ? pixels[outputOffset + x - channels] : 0;
      const up = y > 0 ? pixels[outputOffset + x - stride] : 0;
      const upperLeft = y > 0 && x >= channels ? pixels[outputOffset + x - stride - channels] : 0;
      let value = raw;
      if (filter === 1) value = raw + left;
      else if (filter === 2) value = raw + up;
      else if (filter === 3) value = raw + Math.floor((left + up) / 2);
      else if (filter === 4) value = raw + paethPredictor(left, up, upperLeft);
      else if (filter !== 0) throw new Error(`${path.basename(filePath)} has unsupported PNG filter ${filter}`);
      pixels[outputOffset + x] = value & 0xff;
    }
    inputOffset += stride;
    outputOffset += stride;
  }
  return { width, height, channels, pixels, bytes: buffer.length };
}

function colorDistance(a, b) {
  return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
}

function analyzePng(filePath) {
  const png = decodePng(filePath);
  const colors = new Map();
  const first = [png.pixels[0], png.pixels[1], png.pixels[2]];
  let sampled = 0;
  let ink = 0;
  const step = Math.max(1, VISUAL_BASELINE.sampleStride);
  for (let y = 0; y < png.height; y += step) {
    for (let x = 0; x < png.width; x += step) {
      const offset = (y * png.width + x) * png.channels;
      const rgb = [png.pixels[offset], png.pixels[offset + 1], png.pixels[offset + 2]];
      const key = rgb.join(",");
      colors.set(key, (colors.get(key) || 0) + 1);
      sampled += 1;
      if (colorDistance(rgb, first) > 24) ink += 1;
    }
  }
  const dominant = Math.max(...colors.values());
  return {
    width: png.width,
    height: png.height,
    file_bytes: png.bytes,
    sampled_pixels: sampled,
    unique_colors: colors.size,
    ink_ratio: Number((ink / sampled).toFixed(4)),
    dominant_color_ratio: Number((dominant / sampled).toFixed(4)),
  };
}

function comparePng(currentPath, baselinePath) {
  const current = decodePng(currentPath);
  const baseline = decodePng(baselinePath);
  if (current.width !== baseline.width || current.height !== baseline.height) {
    return {
      status: "dimension_mismatch",
      current_size: `${current.width}x${current.height}`,
      baseline_size: `${baseline.width}x${baseline.height}`,
      diff_ratio: 1,
      mean_pixel_delta: 255,
    };
  }
  const step = Math.max(1, VISUAL_BASELINE.diffSampleStride);
  let sampled = 0;
  let changed = 0;
  let totalDelta = 0;
  for (let y = 0; y < current.height; y += step) {
    for (let x = 0; x < current.width; x += step) {
      const currentOffset = (y * current.width + x) * current.channels;
      const baselineOffset = (y * baseline.width + x) * baseline.channels;
      const currentRgb = [
        current.pixels[currentOffset],
        current.pixels[currentOffset + 1],
        current.pixels[currentOffset + 2],
      ];
      const baselineRgb = [
        baseline.pixels[baselineOffset],
        baseline.pixels[baselineOffset + 1],
        baseline.pixels[baselineOffset + 2],
      ];
      const delta = colorDistance(currentRgb, baselineRgb) / 3;
      sampled += 1;
      totalDelta += delta;
      if (delta > VISUAL_BASELINE.significantPixelDelta) changed += 1;
    }
  }
  return {
    status: "compared",
    sampled_pixels: sampled,
    changed_pixels: changed,
    diff_ratio: Number((changed / sampled).toFixed(4)),
    mean_pixel_delta: Number((totalDelta / sampled).toFixed(2)),
  };
}

function writeVisualBaselineManifest(baselineDir, baselineEntries) {
  fs.mkdirSync(baselineDir, { recursive: true });
  const manifest = {
    version: 1,
    boundary: "Visual baseline for local/staging UI regression only; not production deployment evidence.",
    thresholds: VISUAL_BASELINE,
    screenshots: baselineEntries,
  };
  fs.writeFileSync(
    path.join(baselineDir, VISUAL_BASELINE_MANIFEST),
    JSON.stringify(manifest, null, 2),
    "utf8"
  );
}

function assertVisualBaseline() {
  const failures = [];
  const baselineEntries = {};
  const baselineDir = config.visualBaselineDir || null;
  if (baselineDir && config.updateVisualBaseline) {
    fs.mkdirSync(baselineDir, { recursive: true });
  }
  for (const [name, file] of Object.entries(screenshots)) {
    const metrics = analyzePng(file);
    visual_metrics[name] = metrics;
    if (metrics.file_bytes < VISUAL_BASELINE.minFileBytes) {
      failures.push(`${name} file too small: ${metrics.file_bytes}`);
    }
    if (metrics.unique_colors < VISUAL_BASELINE.minUniqueColors) {
      failures.push(`${name} low color diversity: ${metrics.unique_colors}`);
    }
    if (metrics.ink_ratio < VISUAL_BASELINE.minInkRatio) {
      failures.push(`${name} appears blank: ink_ratio=${metrics.ink_ratio}`);
    }
    if (metrics.dominant_color_ratio > VISUAL_BASELINE.maxDominantColorRatio) {
      failures.push(`${name} dominated by one color: ${metrics.dominant_color_ratio}`);
    }
    if (baselineDir) {
      const baselinePng = path.join(baselineDir, `${name}.png`);
      if (config.updateVisualBaseline) {
        fs.copyFileSync(file, baselinePng);
        baselineEntries[name] = {
          file: `${name}.png`,
          metrics,
        };
      } else if (!fs.existsSync(baselinePng)) {
        failures.push(`${name} missing visual baseline: ${baselinePng}`);
      } else {
        const diff = comparePng(file, baselinePng);
        visual_diffs[name] = diff;
        if (diff.status === "dimension_mismatch") {
          failures.push(
            `${name} baseline dimension mismatch: current=${diff.current_size} baseline=${diff.baseline_size}`
          );
        }
        if (diff.diff_ratio > VISUAL_BASELINE.maxPixelDiffRatio) {
          failures.push(`${name} pixel diff ratio too high: ${diff.diff_ratio}`);
        }
        if (diff.mean_pixel_delta > VISUAL_BASELINE.maxMeanPixelDelta) {
          failures.push(`${name} mean pixel delta too high: ${diff.mean_pixel_delta}`);
        }
      }
    }
  }
  if (baselineDir && config.updateVisualBaseline) {
    writeVisualBaselineManifest(baselineDir, baselineEntries);
  }
  if (failures.length) {
    fail("visual_pixel_integrity", failures.join("; "));
  } else if (baselineDir && config.updateVisualBaseline) {
    pass("visual_pixel_integrity", "Updated screenshot visual baseline and metrics manifest.");
  } else if (baselineDir) {
    pass("visual_pixel_integrity", "Screenshots match visual baseline within pixel diff thresholds.");
  } else {
    pass(
      "visual_pixel_integrity",
      "Screenshots meet pixel-level nonblank, color diversity, and dominant-color thresholds."
    );
  }
}

async function assertNoHorizontalOverflow(page, name) {
  const sizes = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (sizes.scrollWidth > sizes.clientWidth + 1) {
    throw new Error(`${name} horizontal overflow: ${sizes.scrollWidth} > ${sizes.clientWidth}`);
  }
}

async function checkAdminGraph(browser, viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(config.adminUrl, { waitUntil: "networkidle" });
  await page.click('[data-view="graph"]');
  await page.waitForSelector(".graph-detail");
  await page.waitForSelector("[data-node-id]");
  await page.waitForSelector("[data-edge-id]");
  await assertNoHorizontalOverflow(page, `admin ${label}`);
  await page.locator("[data-edge-id]").first().click();
  const detail = await page.locator(".graph-detail").innerText();
  if (!detail.includes("Source") || !detail.includes("Tenant")) {
    throw new Error(`admin ${label} edge detail missing Source/Tenant`);
  }
  const file = path.join(config.outputDir, `admin-graph-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  screenshots[`admin_${label}`] = file;
  await page.close();
}

async function checkAdminTenants(browser, viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(config.adminUrl, { waitUntil: "networkidle" });
  await page.click('[data-view="tenants"]');
  await page.waitForSelector("text=Tenant Inventory");
  await page.waitForSelector("text=Tenant / Organization Readiness");
  await page.waitForSelector("text=enterprise_idp_sso_validation");
  await page.waitForSelector("text=Tenant Policy Editor");
  await page.fill('input[name="admin_users"]', "admin@example.com");
  await page.fill('input[name="sso_allowed_domains"]', "example.com");
  await page.click('button:has-text("保存策略")');
  await page.waitForSelector("text=configured");
  await assertNoHorizontalOverflow(page, `admin tenants ${label}`);
  const panelText = await page.locator("#panel").innerText();
  if (!panelText.includes("ledger_and_tenant_policy_inventory") || !panelText.includes("Policy editor")) {
    throw new Error(`admin tenants ${label} missing source/policy editor boundary`);
  }
  if (!panelText.includes("open review") || !panelText.includes("Graph") || !panelText.includes("Audit")) {
    throw new Error(`admin tenants ${label} missing readiness counters`);
  }
  if (panelText.includes("tenant_config_editor") || panelText.includes("role_policy_editor")) {
    throw new Error(`admin tenants ${label} still reports policy editor as missing`);
  }
  const file = path.join(config.outputDir, `admin-tenants-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  screenshots[`admin_tenants_${label}`] = file;
  await page.close();
}

async function checkAdminLaunch(browser, viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(config.adminUrl, { waitUntil: "networkidle" });
  await page.click('[data-view="launch"]');
  await page.waitForSelector("text=Launch Readiness");
  await page.waitForSelector("text=Production Evidence");
  await page.waitForSelector("text=production_ready=false");
  await page.waitForSelector("text=production=blocked");
  await page.waitForSelector("text=Real enterprise IdP");
  await page.waitForSelector("text=Admin export/write gate");
  await assertNoHorizontalOverflow(page, `admin launch ${label}`);
  const panelText = await page.locator("#panel").innerText();
  if (!panelText.includes("staging launch readiness only") || !panelText.includes("Production monitoring and alerting")) {
    throw new Error(`admin launch ${label} missing launch boundary or blockers`);
  }
  if (!panelText.includes("production_evidence_manifest") || !panelText.includes("productized_live_long_run")) {
    throw new Error(`admin launch ${label} missing production evidence manifest status`);
  }
  const file = path.join(config.outputDir, `admin-launch-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  screenshots[`admin_launch_${label}`] = file;
  await page.close();
}

async function checkStaticSite(browser, viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(config.staticUrl, { waitUntil: "networkidle" });
  await page.waitForSelector("#graphDetail");
  await page.waitForSelector("[data-node-id]");
  await page.waitForSelector("[data-edge-id]");
  await page.waitForSelector('a[href="https://deerflow.tech"]');
  await assertNoHorizontalOverflow(page, `static ${label}`);
  await page.locator("[data-node-id]").first().click();
  const detail = await page.locator("#graphDetail").innerText();
  if (!detail.includes("Tenant") || !detail.includes("Related edges")) {
    throw new Error(`static ${label} node detail missing Tenant/Related edges`);
  }
  const file = path.join(config.outputDir, `static-site-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  screenshots[`static_${label}`] = file;
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await checkAdminGraph(browser, { width: 1440, height: 1000 }, "desktop");
    pass("admin_desktop_graph", "Graph tab renders selectable edge detail without horizontal overflow.");
    await checkAdminGraph(browser, { width: 390, height: 844 }, "mobile");
    pass("admin_mobile_graph", "Mobile Graph tab renders selectable edge detail without horizontal overflow.");
    await checkAdminTenants(browser, { width: 1440, height: 1000 }, "desktop");
    pass("admin_desktop_tenants", "Tenants tab renders readiness counters, policy editor save, and missing capabilities without horizontal overflow.");
    await checkAdminTenants(browser, { width: 390, height: 844 }, "mobile");
    pass("admin_mobile_tenants", "Mobile Tenants tab renders readiness counters and policy editor without horizontal overflow.");
    await checkAdminLaunch(browser, { width: 1440, height: 1000 }, "desktop");
    pass("admin_desktop_launch", "Launch tab renders staging readiness and production blockers without horizontal overflow.");
    await checkAdminLaunch(browser, { width: 390, height: 844 }, "mobile");
    pass("admin_mobile_launch", "Mobile Launch tab renders readiness gates without horizontal overflow.");
    await checkStaticSite(browser, { width: 1440, height: 1000 }, "desktop");
    pass("static_desktop_site", "Static site renders graph detail and Deerflow attribution.");
    await checkStaticSite(browser, { width: 390, height: 844 }, "mobile");
    pass("static_mobile_site", "Mobile static site renders graph detail without horizontal overflow.");
    assertVisualBaseline();
  } catch (error) {
    fail("playwright", error.message);
  } finally {
    await browser.close();
  }
  const ok = Object.values(checks).every((check) => check.status === "pass");
  console.log(JSON.stringify({ ok, checks, screenshots, visual_metrics, visual_diffs }, null, 2));
})();
"""


if __name__ == "__main__":
    raise SystemExit(main())
