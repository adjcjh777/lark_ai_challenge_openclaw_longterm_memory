import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
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
  const larkProfile = env.LARK_CLI_PROFILE || "feishu-ai-challenge";
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
  const result = await runCommand(command, {
    cwd: options.cwd,
    env,
    timeoutSeconds: env.FEISHU_CARD_TIMEOUT_SECONDS || 5,
  });
  return {
    ...result,
    mode: messageId ? "reply_card" : "send_card",
    delivery_mode: "chat",
    reply_to: messageId || null,
    chat_id: chatId || null,
    card: publish.card,
    text: "",
    fallback_used: false,
    fallback_suppressed: !result.ok,
    fallback_reason: result.ok ? undefined : commandFailureReason(result),
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
    LARK_CLI_PROFILE: env.LARK_CLI_PROFILE || "feishu-ai-challenge",
  };
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

export function buildCardDeliveryFailureFallback(cardDelivery) {
  const reason = cardDelivery?.timed_out
    ? "interactive card delivery timed out"
    : String(cardDelivery?.stderr || cardDelivery?.fallback_reason || "interactive card delivery failed");
  const cardSummary = extractCardTextFallback(cardDelivery?.card);
  const lines = [
    "Memory Copilot 已收到这条消息，但卡片投递失败。",
    "",
    `状态：card_delivery_failed`,
    `原因：${truncateForOperator(reason, 180)}`,
    "处理：OpenClaw 和 Memory Copilot 路由仍在线；已降级为文本结果。",
  ];
  if (cardSummary) {
    lines.push("", "卡片内容：", cardSummary);
  }
  return lines.join("\n");
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

export function extractCardTextFallback(card) {
  const lines = [];
  collectCardText(card?.header?.title, lines);
  const elements = Array.isArray(card?.elements) ? card.elements : [];
  for (const element of elements) {
    collectCardText(element?.text, lines);
    const fields = Array.isArray(element?.fields) ? element.fields : [];
    for (const field of fields) {
      collectCardText(field?.text, lines);
    }
    const actions = Array.isArray(element?.actions) ? element.actions : [];
    for (const action of actions) {
      collectCardText(action?.text, lines);
    }
  }
  const normalized = lines
    .map((line) => String(line || "").replace(/\*\*/g, "").trim())
    .filter(Boolean);
  return truncateForOperator(normalized.join("\n"), 1200);
}

function collectCardText(node, lines) {
  if (!node || typeof node !== "object") {
    return;
  }
  if (typeof node.content === "string") {
    lines.push(node.content);
  }
  if (typeof node.text === "string") {
    lines.push(node.text);
  }
}

function hashString(input) {
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) {
    hash = ((hash << 5) - hash + input.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(16);
}
