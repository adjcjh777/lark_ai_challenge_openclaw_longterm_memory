import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";

export async function runCommand(command, options = {}) {
  const child = spawn(command[0], command.slice(1), {
    cwd: options.cwd || process.cwd(),
    env: options.env || process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stdoutChunks = [];
  const stderrChunks = [];
  child.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
  child.stderr.on("data", (chunk) => stderrChunks.push(chunk));

  const timeoutMs = Math.max(1, Number(options.timeoutSeconds || 2)) * 1000;
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    child.kill("SIGTERM");
  }, timeoutMs);

  const exitCode = await new Promise((resolveExit) => {
    child.on("close", resolveExit);
    child.on("error", (error) => {
      stderrChunks.push(Buffer.from(String(error?.message || error || "spawn failed")));
      resolveExit(1);
    });
  });
  clearTimeout(timer);
  return {
    ok: exitCode === 0 && !timedOut,
    returncode: exitCode,
    stdout: Buffer.concat(stdoutChunks).toString("utf8").trim(),
    stderr: Buffer.concat(stderrChunks).toString("utf8").trim(),
    timed_out: timedOut,
  };
}

export async function publishInteractiveCardViaLarkCli(publish, options = {}) {
  if (!publish || publish.mode !== "interactive" || !publish.card || publish.delivery_mode !== "chat") {
    return null;
  }
  const rawMessageId = String(publish.reply_to || "").trim();
  const messageId = isRealFeishuMessageId(rawMessageId) ? rawMessageId : "";
  const chatId = String(publish.chat_id || "").trim();
  if (!messageId && !chatId) {
    return {
      ok: false,
      mode: "interactive",
      stderr: "interactive card publish missing reply_to and chat_id",
      fallback_used: false,
      fallback_suppressed: true,
    };
  }
  const env = larkCliEnvironment(options.env || process.env);
  const larkCli = resolveLarkCliBin(env);
  const larkProfile = resolveLarkCliProfile(env);
  const larkAs = env.LARK_CLI_AS || "bot";
  const command = [larkCli, "--profile", larkProfile];
  command.push("api", "POST");
  if (messageId) {
    command.push(`/open-apis/im/v1/messages/${messageId}/reply`);
  } else {
    command.push("/open-apis/im/v1/messages");
  }
  command.push("--as", larkAs);
  if (!messageId) {
    command.push("--params", JSON.stringify({ receive_id_type: "chat_id" }));
  }
  command.push("--data", JSON.stringify(buildInteractiveCardRequestBody({
    card: publish.card,
    chatId,
    messageId,
    uuid: interactiveCardIdempotencyKey(publish),
  })));
  const command_preview = commandPreview(command);
  const result = await runCommand(command, {
    cwd: options.cwd,
    env,
    timeoutSeconds: env.FEISHU_CARD_TIMEOUT_SECONDS || 5,
  });
  return {
    ...result,
    mode: messageId ? "reply_card" : "send_card",
    delivery_mode: "chat",
    command_preview,
    reply_to: messageId || null,
    chat_id: chatId || null,
    card: publish.card,
    text: "",
    fallback_used: false,
    fallback_suppressed: !result.ok,
    fallback_reason: result.ok ? undefined : commandFailureReason(result),
  };
}

export async function addFeishuTypingIndicatorViaLarkCli(messageId, options = {}) {
  const realMessageId = isRealFeishuMessageId(messageId) ? String(messageId).trim() : "";
  if (!realMessageId) {
    return null;
  }
  const env = larkCliEnvironment(options.env || process.env);
  const larkCli = resolveLarkCliBin(env);
  const larkProfile = resolveLarkCliProfile(env);
  const larkAs = env.LARK_CLI_AS || "bot";
  const command = [
    larkCli,
    "--profile",
    larkProfile,
    "api",
    "POST",
    `/open-apis/im/v1/messages/${realMessageId}/reactions`,
    "--as",
    larkAs,
    "--data",
    JSON.stringify({ reaction_type: { emoji_type: "Typing" } }),
  ];
  const command_preview = commandPreview(command);
  const result = await runCommand(command, {
    cwd: options.cwd,
    env,
    timeoutSeconds: env.FEISHU_REACTION_TIMEOUT_SECONDS || env.FEISHU_CARD_TIMEOUT_SECONDS || 3,
  });
  return {
    ...result,
    mode: "typing_reaction",
    command_preview,
    message_id: realMessageId,
    reaction_id: parseReactionId(result.stdout),
  };
}

export function larkCliEnvironment(env = process.env) {
  const home = env.HOME || homedir() || "/Users/junhaocheng";
  const path = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    env.PATH,
  ].filter(Boolean).join(":");
  return {
    ...env,
    HOME: home,
    USER: env.USER || "junhaocheng",
    PATH: path,
    LARK_CLI_PROFILE: env.LARK_CLI_PROFILE || resolveLarkCliProfile({ ...env, HOME: home }),
  };
}

export function resolveLarkCliProfile(env = process.env) {
  if (env.LARK_CLI_PROFILE) {
    return env.LARK_CLI_PROFILE;
  }
  if (env.OPENCLAW_SERVICE_MARKER || env.OPENCLAW_SERVICE_KIND) {
    const profile = readFirstOpenClawBoundLarkProfile(env.HOME || homedir());
    if (profile) {
      return profile;
    }
  }
  return "feishu-ai-challenge";
}

function readFirstOpenClawBoundLarkProfile(home) {
  if (!home) {
    return "";
  }
  const configPath = `${home}/.lark-cli/openclaw/config.json`;
  try {
    const raw = JSON.parse(readFileSync(configPath, "utf8"));
    const app = Array.isArray(raw?.apps) ? raw.apps.find((item) => item?.name || item?.appId) : null;
    return String(app?.name || app?.appId || "").trim();
  } catch (_) {
    return "";
  }
}

export function resolveLarkCliBin(env = process.env) {
  if (env.LARK_CLI_BIN) {
    return env.LARK_CLI_BIN;
  }
  const candidates = [
    "/opt/homebrew/bin/lark-cli",
    "/usr/local/bin/lark-cli",
    "lark-cli",
  ];
  return candidates.find((candidate) => candidate === "lark-cli" || existsSync(candidate)) || "lark-cli";
}

export function buildInteractiveCardRequestBody({ card, chatId, messageId, uuid }) {
  const body = {
    msg_type: "interactive",
    content: JSON.stringify(card || {}),
    uuid,
  };
  if (messageId) {
    return body;
  }
  return {
    ...body,
    receive_id: chatId,
  };
}

export function interactiveCardIdempotencyKey(publish) {
  const raw = [
    "openclaw-card",
    publish.reply_to || "",
    publish.chat_id || "",
    JSON.stringify(publish.card || {}),
  ].join("|");
  return `fmc_openclaw_${hashString(raw)}`;
}

export function isRealFeishuMessageId(value) {
  return /^om_[A-Za-z0-9_-]+$/.test(String(value || "").trim());
}

export function commandFailureReason(result) {
  const detail = truncateForOperator(
    [result?.stderr, result?.stdout].filter(Boolean).join(" "),
    240,
  );
  if (!detail) {
    return "openclaw_gateway_interactive_card_failed";
  }
  return `openclaw_gateway_interactive_card_failed: ${detail}`;
}

function parseReactionId(stdout) {
  try {
    const payload = JSON.parse(String(stdout || "{}"));
    return String(payload?.data?.reaction_id || "").trim();
  } catch (_) {
    return "";
  }
}

export function commandPreview(command) {
  const preview = [];
  for (let index = 0; index < command.length; index += 1) {
    const value = String(command[index] || "");
    if (index === 0) {
      preview.push(value.split("/").pop() || value);
      continue;
    }
    preview.push(value);
    if (value === "--data" || value === "--params") {
      index += 1;
      preview.push("<json>");
    }
  }
  return preview.join(" ");
}

export function buildRouterFailureFallback(error) {
  return [
    "Memory Copilot 已收到这条消息，但路由处理失败。",
    "",
    "状态：router_failed",
    `原因：${truncateForOperator(String(error), 180)}`,
    "处理：OpenClaw 仍在线；请查看本机 gateway 日志和 Copilot router 日志。",
  ].join("\n");
}

export function truncateForOperator(value, maxLength) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 3))}...`;
}

function hashString(input) {
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) {
    hash = ((hash << 5) - hash + input.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(16);
}
