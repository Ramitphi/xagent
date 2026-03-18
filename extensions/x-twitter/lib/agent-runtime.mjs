import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { safeTweetText } from "./utils.mjs";

const execFileAsync = promisify(execFile);

function buildPrompt({ mention, persona, conversation }) {
  const conversationContract = conversation?.contract || "";
  const conversationChain = conversation?.chain || "";

  return [
    "You are replying to an X mention through OpenClaw's embedded runtime.",
    "Use the workspace persona and skills.",
    "If the user is asking for EVM contract analysis, use the on-chain-wizard skill.",
    "The skill already handles contract validation, submit, poll, and structured analysis.",
    "Do not mention @OWAIbot in your reply text.",
    "Preserve full URLs exactly.",
    "If contract or chain is missing, ask for it instead of guessing.",
    "If the user is greeting or asking for an intro, reply warmly and naturally.",
    "If this is a retry in the same thread and prior contract+chain exist, you may reuse them.",
    "",
    "Return ONLY valid JSON with this exact shape:",
    '{"type":"single_reply|ack_then_reply|skip","text":"...", "ack":"...", "conversationContract":"...", "conversationChain":"..."}',
    "Rules:",
    '- For "single_reply", include "text" and omit "ack".',
    '- For "ack_then_reply", include both "ack" and "text".',
    '- For "skip", omit "text" and "ack".',
    '- conversationContract and conversationChain are optional and only used when you want the channel to persist reusable thread context.',
    "",
    "Persona:",
    persona,
    "",
    "Mention envelope:",
    JSON.stringify({
      mentionText: mention.text || "",
      parentText: mention.parentText || "",
      authorId: mention.authorId || "",
      authorUsername: mention.authorUsername || "",
      conversationId: mention.conversationId || "",
      replyToTweetId: mention.replyToTweetId || "",
      socialIntentHint: mention.socialHint || "",
      isRetryRequest: Boolean(mention.isRetryRequest),
      storedConversationContract: conversationContract,
      storedConversationChain: conversationChain,
      targetTweetId: mention.id || ""
    })
  ].join("\n");
}

function parseReplyPlan(stdout) {
  const trimmed = String(stdout || "").trim();
  if (!trimmed) {
    throw new Error("OpenClaw agent returned empty output");
  }

  let parsed;
  try {
    parsed = JSON.parse(trimmed);
  } catch (error) {
    throw new Error(`OpenClaw agent returned non-JSON output: ${trimmed}`);
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("OpenClaw agent returned invalid reply plan");
  }

  const type = parsed.type;
  if (!["single_reply", "ack_then_reply", "skip"].includes(type)) {
    throw new Error(`OpenClaw agent returned unsupported plan type: ${type}`);
  }

  return {
    type,
    text: parsed.text ? safeTweetText(parsed.text) : "",
    ack: parsed.ack ? safeTweetText(parsed.ack) : "",
    conversationContract: parsed.conversationContract || "",
    conversationChain: parsed.conversationChain || ""
  };
}

export async function invokeAgentRuntime({ mention, persona, conversation }) {
  const prompt = buildPrompt({ mention, persona, conversation });
  const target = mention.conversationId
    ? `x-twitter:${mention.conversationId}`
    : `x-twitter:tweet:${mention.id}`;

  const { stdout, stderr } = await execFileAsync(
    "openclaw",
    [
      "agent",
      "--local",
      "--to",
      target,
      "--message",
      prompt
    ],
    {
      maxBuffer: 1024 * 1024,
      env: process.env
    }
  );

  if (stderr && String(stderr).trim()) {
    const err = String(stderr).trim();
    if (/error/i.test(err)) {
      throw new Error(`OpenClaw agent stderr: ${err}`);
    }
  }

  return parseReplyPlan(stdout);
}
