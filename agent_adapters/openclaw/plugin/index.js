import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { jsonResult } from "openclaw/plugin-sdk/core";

const PLUGIN_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(PLUGIN_DIR, "../../..");
const SCHEMA_PATH = resolve(REPO_ROOT, "agent_adapters/openclaw/memory_tools.schema.json");
const PYTHON = process.env.FEISHU_MEMORY_COPILOT_PYTHON || "python3";
let adminDashboardStarted = false;

// Translation map: OpenClaw-facing tool names (fmc_xxx) → Python-side tool names (memory.xxx)
const OPENCLAW_TO_PYTHON = {
  fmc_memory_search: "memory.search",
  fmc_memory_create_candidate: "memory.create_candidate",
  fmc_memory_confirm: "memory.confirm",
  fmc_memory_reject: "memory.reject",
  fmc_memory_explain_versions: "memory.explain_versions",
  fmc_memory_prefetch: "memory.prefetch",
  fmc_heartbeat_review_due: "heartbeat.review_due",
};

function loadToolSpecs() {
  const raw = readFileSync(SCHEMA_PATH, "utf8");
  const schema = JSON.parse(raw);
  if (!Array.isArray(schema.tools)) {
    throw new Error("memory_tools.schema.json must contain a tools array");
  }
  return schema.tools.map((toolSpec) => ({
    ...toolSpec,
    input_schema: attachSchemaDefinitions(toolSpec.input_schema, schema.$defs),
  }));
}

function attachSchemaDefinitions(inputSchema, definitions) {
  const schema = JSON.parse(JSON.stringify(inputSchema));
  if (definitions && typeof definitions === "object" && !schema.$defs) {
    schema.$defs = definitions;
  }
  return schema;
}

function createTool(toolSpec) {
  return {
    name: toolSpec.name,
    label: toolSpec.name,
    description: toolSpec.description,
    parameters: toolSpec.input_schema,
    execute: async (_toolCallId, rawParams) => {
      const pythonToolName = OPENCLAW_TO_PYTHON[toolSpec.name] || toolSpec.name;
      const output = await runPythonTool(pythonToolName, normalizeToolPayload(rawParams || {}));
      return jsonResult(output);
    },
  };
}

function normalizeToolPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return payload;
  }
  const normalized = { ...payload };
  normalized.current_context = parseJsonObjectString(normalized.current_context);
  return normalized;
}

function parseJsonObjectString(value) {
  if (typeof value !== "string") {
    return value;
  }
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return value;
  }
  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : value;
  } catch {
    return value;
  }
}

async function runPythonTool(toolName, payload) {
  const envelope = {
    tool: toolName,
    payload,
    db_path: process.env.FEISHU_MEMORY_COPILOT_DB || undefined,
  };
  const child = spawn(PYTHON, ["-m", "memory_engine.copilot.openclaw_tool_runner"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PYTHONPATH: [REPO_ROOT, process.env.PYTHONPATH].filter(Boolean).join(":"),
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  const stdoutChunks = [];
  const stderrChunks = [];
  child.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
  child.stderr.on("data", (chunk) => stderrChunks.push(chunk));

  child.stdin.end(JSON.stringify(envelope));

  const exitCode = await new Promise((resolveExit) => {
    child.on("close", resolveExit);
  });
  const stdout = Buffer.concat(stdoutChunks).toString("utf8").trim();
  const stderr = Buffer.concat(stderrChunks).toString("utf8").trim();

  if (exitCode !== 0) {
    throw new Error(`Feishu Memory Copilot tool runner failed for ${toolName}: ${stderr || stdout || exitCode}`);
  }
  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw new Error(`Feishu Memory Copilot tool runner returned invalid JSON for ${toolName}: ${String(error)}`);
  }
}

function startAdminDashboard() {
  if (adminDashboardStarted || !adminDashboardEnabled()) {
    return;
  }
  adminDashboardStarted = true;
  const host = process.env.FEISHU_MEMORY_COPILOT_ADMIN_HOST || process.env.COPILOT_ADMIN_HOST || "127.0.0.1";
  const port = process.env.FEISHU_MEMORY_COPILOT_ADMIN_PORT || process.env.COPILOT_ADMIN_PORT || "8765";
  const dbPath = process.env.FEISHU_MEMORY_COPILOT_DB || process.env.MEMORY_DB_PATH || "data/memory.sqlite";
  const child = spawn(PYTHON, [
    "scripts/start_copilot_admin.py",
    "--host",
    host,
    "--port",
    String(port),
    "--db-path",
    dbPath,
    "--init-db-if-missing",
  ], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PYTHONPATH: [REPO_ROOT, process.env.PYTHONPATH].filter(Boolean).join(":"),
    },
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

function adminDashboardEnabled() {
  const raw = process.env.FEISHU_MEMORY_COPILOT_ADMIN_ENABLED || process.env.COPILOT_ADMIN_ENABLED;
  return raw && ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

export default definePluginEntry({
  id: "feishu-memory-copilot",
  name: "Feishu Memory Copilot",
  description: "First-class OpenClaw memory tools backed by CopilotService.",
  kind: "tool",
  register(api) {
    startAdminDashboard();
    api.registerTool(() => {
      const specs = loadToolSpecs();
      return specs.map(createTool);
    }, {
      names: [
        "fmc_memory_search",
        "fmc_memory_create_candidate",
        "fmc_memory_confirm",
        "fmc_memory_reject",
        "fmc_memory_explain_versions",
        "fmc_memory_prefetch",
        "fmc_heartbeat_review_due",
      ],
    });
  },
});
