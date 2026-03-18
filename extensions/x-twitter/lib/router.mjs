import fs from "node:fs/promises";
import path from "node:path";

import { invokeAgentRuntime } from "./agent-runtime.mjs";
import {
  SUPPORTED_CHAINS,
  hashText,
  isRetryRequest,
  isValidContract,
  safeTweetText,
  socialIntentHint
} from "./utils.mjs";

const DEFAULT_PERSONA_PROMPT = "You are OWAIbot, a friendly human-like analyst on X. You help with onchain analysis and also converse naturally in short, helpful replies.";

async function loadPersona(rootDir) {
  try {
    const text = await fs.readFile(path.join(rootDir, "agent.md"), "utf8");
    return text.trim() || DEFAULT_PERSONA_PROMPT;
  } catch {
    return DEFAULT_PERSONA_PROMPT;
  }
}

function normalizeConversationState(plan) {
  const contract = String(plan.conversationContract || "").trim();
  const chain = String(plan.conversationChain || "").trim().toLowerCase();
  if (!contract || !isValidContract(contract) || !chain || !SUPPORTED_CHAINS.has(chain)) {
    return null;
  }
  return { contract, chain };
}

export async function buildReplyPlan({ mention, state, config, rootDir }) {
  const persona = await loadPersona(rootDir);
  const mentionText = mention.text || "";
  const socialHint = socialIntentHint(mentionText);
  const mentionHash = hashText(mentionText.toLowerCase().trim());
  const recentReply = state.recentGeneralRepliesByUser?.[mention.authorId || ""] || null;
  const conversation = state.conversationContexts?.[mention.conversationId || ""] || {};

  const cooldownSeconds = Number(config.generalReplyCooldownSeconds || 600);
  const now = Math.floor(Date.now() / 1000);
  const withinCooldown = recentReply && (now - Number(recentReply.lastTimestamp || 0) < cooldownSeconds);
  const repeatedSocialPing = Boolean(
    withinCooldown &&
    ["greeting", "intro"].includes(socialHint) &&
    (recentReply.lastSocialHint === socialHint || recentReply.lastMentionHash === mentionHash)
  );

  if (repeatedSocialPing) {
    return { type: "skip" };
  }

  const runtimePlan = await invokeAgentRuntime({
    mention: {
      ...mention,
      socialHint,
      isRetryRequest: isRetryRequest(mentionText)
    },
    persona,
    conversation
  });

  if (runtimePlan.type === "skip") {
    return { type: "skip" };
  }

  if (runtimePlan.type === "single_reply") {
    return {
      type: "single_reply",
      text: safeTweetText(runtimePlan.text),
      conversationState: normalizeConversationState(runtimePlan),
      generalReplyRecord: runtimePlan.text ? {
        lastText: runtimePlan.text,
        lastTextHash: hashText(runtimePlan.text),
        lastMentionHash: mentionHash,
        lastSocialHint: socialHint
      } : null
    };
  }

  return {
    type: "ack_then_reply",
    ack: safeTweetText(runtimePlan.ack),
    text: safeTweetText(runtimePlan.text),
    conversationState: normalizeConversationState(runtimePlan)
  };
}
