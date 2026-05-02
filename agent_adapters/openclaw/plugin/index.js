import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { jsonResult } from "openclaw/plugin-sdk/core";
import {
  buildCardDeliveryFailureFallback,
  buildRouterFailureFallback,
  publishInteractiveCardViaLarkCli,
} from "./feishu_card_delivery.js";

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

const FEISHU_GROUP_ROUTER_COMMANDS = new Set([
  "settings",
  "group_settings",
  "recall",
  "memory_search",
  "search_memory",
  "prefetch",
  "memory_prefetch",
  "prefetch_memory",
  "review",
  "inbox",
  "review_inbox",
  "enable_memory",
  "memory_on",
  "enable_group_memory",
  "disable_memory",
  "memory_off",
  "disable_group_memory",
]);

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

async function runPythonFeishuRouter(payload) {
  const child = spawn(PYTHON, ["scripts/openclaw_feishu_remember_router.py"], {
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
  child.stdin.end(JSON.stringify({
    ...payload,
    db_path: process.env.FEISHU_MEMORY_COPILOT_DB || undefined,
  }));

  const exitCode = await new Promise((resolveExit) => {
    child.on("close", resolveExit);
  });
  const stdout = Buffer.concat(stdoutChunks).toString("utf8").trim();
  const stderr = Buffer.concat(stderrChunks).toString("utf8").trim();
  if (exitCode !== 0) {
    throw new Error(`Feishu Memory Copilot router failed: ${stderr || stdout || exitCode}`);
  }
  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw new Error(`Feishu Memory Copilot router returned invalid JSON: ${String(error)}`);
  }
}

function registerFeishuBeforeDispatchHook(api) {
  if (typeof api.on !== "function") {
    api.logger?.warn?.("typed hook API is unavailable; Feishu before_dispatch router not registered");
    return;
  }
  api.on("before_dispatch", async (event, context) => {
    if (!shouldRouteFeishuGroupEvent(event, context)) {
      return undefined;
    }
    try {
      const result = await runPythonFeishuRouter({
        text: String(event.content || event.body || ""),
        message_id: deriveMessageId(event, context),
        chat_id: deriveChatId(event, context),
        sender_open_id: String(event.senderId || context.senderId || ""),
        chat_type: event.isGroup ? "group" : "p2p",
        bot_mentioned: false,
      });
      api.logger?.info?.(`feishu-memory-copilot route result ${JSON.stringify(sanitizeRouteResult(result))}`);
      const publish = result && typeof result === "object" ? result.publish : null;
      const cardDelivery = await publishInteractiveCardViaLarkCli(publish);
      if (cardDelivery) {
        api.logger?.info?.(`feishu-memory-copilot card delivery ${JSON.stringify(sanitizePublish(cardDelivery))}`);
        if (!cardDelivery.ok) {
          return { handled: true, text: buildCardDeliveryFailureFallback(cardDelivery) };
        }
        return { handled: true };
      }
      if (publish && publish.mode === "reply" && typeof publish.text === "string" && publish.text.trim()) {
        return { handled: true, text: publish.text };
      }
      return { handled: true };
    } catch (error) {
      api.logger?.error?.(`feishu-memory-copilot router failed ${String(error)}`);
      return { handled: true, text: buildRouterFailureFallback(error) };
    }
  }, {
    name: "feishu-memory-copilot-before-dispatch",
    description: "Routes Feishu group messages through the Copilot router before generic agent dispatch.",
  });
}

function sanitizeRouteResult(result) {
  if (!result || typeof result !== "object") {
    return { ok: false, reason: "non_object_result" };
  }
  const toolResult = result.tool_result && typeof result.tool_result === "object" ? result.tool_result : {};
  const bridge = toolResult.bridge && typeof toolResult.bridge === "object" ? toolResult.bridge : {};
  return {
    ok: result.ok,
    tool: result.tool,
    routing_reason: result.routing_reason,
    message_id: redactId(result.message_id),
    chat_id: redactId(result.chat_id),
    publish: sanitizePublish(result.publish),
    card: sanitizeCard(result.card),
    tool_result: {
      ok: toolResult.ok,
      tool: toolResult.tool,
      status: toolResult.status,
      action: toolResult.action,
      bridge: sanitizeBridge(bridge),
    },
  };
}

function sanitizePublish(publish) {
  if (!publish || typeof publish !== "object") {
    return {};
  }
  const targets = Array.isArray(publish.targets) ? publish.targets.map(redactId) : undefined;
  return {
    ok: publish.ok,
    mode: publish.mode,
    delivery_mode: publish.delivery_mode,
    targets,
    card: sanitizeCard(publish.card),
    fallback_used: publish.fallback_used,
    fallback_suppressed: publish.fallback_suppressed,
    fallback_reason: publish.fallback_reason,
    suppressed: publish.suppressed,
  };
}

function sanitizeCard(card) {
  if (!card || typeof card !== "object") {
    return undefined;
  }
  const openIds = Array.isArray(card.open_ids) ? card.open_ids.map(redactId) : undefined;
  const actionElements = sanitizeCardActionElements(card);
  if (openIds || actionElements.length > 0) {
    return {
      open_ids: openIds,
      elements: actionElements.length > 0 ? actionElements : undefined,
    };
  }
  return undefined;
}

function sanitizeCardActionElements(card) {
  const elements = Array.isArray(card.elements) ? card.elements : [];
  const actionElements = [];
  for (const element of elements) {
    if (!element || typeof element !== "object" || element.tag !== "action" || !Array.isArray(element.actions)) {
      continue;
    }
    const actions = [];
    for (const action of element.actions) {
      const value = action && typeof action === "object" && action.value && typeof action.value === "object"
        ? action.value
        : {};
      if (value.memory_engine_action) {
        actions.push({ value: { memory_engine_action: String(value.memory_engine_action) } });
      }
    }
    if (actions.length > 0) {
      actionElements.push({ tag: "action", actions });
    }
  }
  return actionElements;
}

function sanitizeBridge(bridge) {
  const decision = bridge.permission_decision && typeof bridge.permission_decision === "object"
    ? bridge.permission_decision
    : {};
  return {
    entrypoint: bridge.entrypoint,
    tool: bridge.tool,
    request_id: bridge.request_id ? "present" : "",
    trace_id: bridge.trace_id ? "present" : "",
    permission_decision: {
      decision: decision.decision,
      reason_code: decision.reason_code,
      source_entrypoint: decision.source_entrypoint,
    },
  };
}

function redactId(value) {
  const raw = String(value || "");
  if (!raw) {
    return "";
  }
  if (raw.length <= 8) {
    return "***";
  }
  return `${raw.slice(0, 4)}...${raw.slice(-4)}`;
}

function shouldRouteFeishuGroupEvent(event, context) {
  const channel = String(event.channel || context.channelId || "").toLowerCase();
  if (channel !== "feishu") {
    return false;
  }
  if (event.isGroup !== true) {
    return false;
  }
  const text = String(event.content || event.body || "").trim();
  if (!text) {
    return false;
  }
  const commandName = slashCommandName(text);
  if (commandName && FEISHU_GROUP_ROUTER_COMMANDS.has(commandName)) {
    return true;
  }
  if (containsFirstClassToolPrompt(text)) {
    return false;
  }
  if (isExplicitRemember(text)) {
    return true;
  }
  return true;
}

function slashCommandName(text) {
  const stripped = text.trim();
  if (!stripped.startsWith("/")) {
    return "";
  }
  return stripped.slice(1).split(/\s+/, 1)[0].trim().toLowerCase();
}

function isExplicitRemember(text) {
  const lowered = text.trim().toLowerCase();
  return lowered === "/remember" || lowered.startsWith("/remember ");
}

function containsFirstClassToolPrompt(text) {
  return /\bfmc_(?:memory|heartbeat)_/.test(text) || /\bmemory\.(?:search|prefetch|create_candidate|confirm|reject|explain_versions)\b/.test(text);
}

function deriveMessageId(event, context) {
  const direct = event.messageId || context.messageId;
  if (direct) {
    return String(direct);
  }
  return `openclaw_before_dispatch_${hashString([
    event.channel,
    context.conversationId,
    event.senderId || context.senderId,
    event.timestamp,
    event.content || event.body || "",
  ].join("|"))}`;
}

function deriveChatId(event, context) {
  const candidates = [
    context.conversationId,
    event.sessionKey,
    context.sessionKey,
    event.content,
    event.body,
  ];
  for (const candidate of candidates) {
    const match = String(candidate || "").match(/\boc_[A-Za-z0-9_-]+\b/);
    if (match) {
      return match[0];
    }
  }
  return String(context.conversationId || event.sessionKey || context.sessionKey || "");
}

function hashString(input) {
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) {
    hash = ((hash << 5) - hash + input.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(16);
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
    registerFeishuBeforeDispatchHook(api);
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
