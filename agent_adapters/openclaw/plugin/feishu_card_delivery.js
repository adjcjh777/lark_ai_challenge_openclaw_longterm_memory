import { spawn } from "node:child_process";

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
    child.on("error", () => resolveExit(1));
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
  const env = options.env || process.env;
  const larkCli = env.LARK_CLI_BIN || "lark-cli";
  const larkAs = env.LARK_CLI_AS || "bot";
  const command = [larkCli];
  if (env.LARK_CLI_PROFILE) {
    command.push("--profile", env.LARK_CLI_PROFILE);
  }
  command.push("im");
  command.push(messageId ? "+messages-reply" : "+messages-send");
  command.push("--as", larkAs);
  if (messageId) {
    command.push("--message-id", messageId);
  } else {
    command.push("--chat-id", chatId);
  }
  command.push("--msg-type", "interactive");
  command.push("--content", JSON.stringify(publish.card));
  command.push("--idempotency-key", interactiveCardIdempotencyKey(publish));
  const result = await runCommand(command, {
    cwd: options.cwd,
    env,
    timeoutSeconds: env.FEISHU_CARD_TIMEOUT_SECONDS || 2,
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
    fallback_reason: result.ok ? undefined : "openclaw_gateway_interactive_card_failed",
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
    : String(cardDelivery?.fallback_reason || cardDelivery?.stderr || "interactive card delivery failed");
  return [
    "Memory Copilot 已收到这条消息，但卡片投递失败。",
    "",
    `状态：card_delivery_failed`,
    `原因：${truncateForOperator(reason, 180)}`,
    "处理：OpenClaw 和 Memory Copilot 路由仍在线；请检查 lark-cli / interactive card 发送权限和本机日志。",
  ].join("\n");
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
