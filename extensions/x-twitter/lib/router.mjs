import fs from "node:fs/promises";
import path from "node:path";

import { analyzeContract } from "./onchain-skill.mjs";
import { classifyMention, draftGeneralReply, draftOnchainReply } from "./openai.mjs";
import {
  SUPPORTED_CHAINS,
  extractChain,
  extractContractAddress,
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

function formatOnchainResult(payload) {
  if (payload.status === "failed") {
    const error = String(payload.error || "Unknown failure");
    if (error.includes("Could not fetch ABI")) {
      return "This contract is not verified on the explorer, so I cannot auto-fetch the ABI. Reply with ABI JSON and I can retry.";
    }
    return `Analysis failed: ${error}`;
  }

  const result = payload.result || {};
  const tldr = String(result.tldr || "").replace(/\n/g, " ").trim();
  const dashboard = String(result.dashboardUrl || payload.dashboardUrl || "");
  const firstMethod = Array.isArray(result.topMethods) ? result.topMethods[0] : null;
  const topLine = firstMethod
    ? ` Top: ${firstMethod.function_name || "unknown_fn"} (${firstMethod.call_count ?? "?"} calls, ${firstMethod.unique_callers ?? "?"} callers).`
    : "";
  let summary = tldr ? `TLDR: ${tldr}` : "Analysis completed.";
  if (dashboard) {
    summary += ` Dashboard: ${dashboard}.`;
  }
  summary += topLine;
  return safeTweetText(summary);
}

export async function buildReplyPlan({ mention, state, config, rootDir }) {
  const persona = await loadPersona(rootDir);
  const mentionText = mention.text || "";
  const parentText = mention.parentText || "";
  const contextText = `${mentionText}\n${parentText}`.trim();
  const socialHint = socialIntentHint(mentionText);
  const conversation = state.conversationContexts?.[mention.conversationId || ""] || {};
  const mentionHash = hashText(mentionText.toLowerCase().trim());
  const recentReply = state.recentGeneralRepliesByUser?.[mention.authorId || ""] || null;

  const context = {
    mentionText,
    parentText,
    contextText,
    authorUsername: mention.authorUsername || "",
    socialHint
  };

  const useLlm = Boolean(process.env.OPENAI_API_KEY);
  let decision = {
    intent: "general",
    contract: null,
    chain: null,
    confidence: 0
  };

  if (useLlm) {
    try {
      decision = await classifyMention(context);
    } catch {
      decision = { intent: "general", contract: null, chain: null, confidence: 0 };
    }
  }

  if (decision.intent === "onchain_analysis" && Number(decision.confidence || 0) >= 0.65) {
    let contract = decision.contract;
    let chain = decision.chain;
    if (!contract && conversation.contract && isRetryRequest(mentionText)) {
      contract = conversation.contract;
    }
    if (!chain && conversation.chain && isRetryRequest(mentionText)) {
      chain = conversation.chain;
    }
    if (!contract || !isValidContract(contract)) {
      return {
        type: "single_reply",
        text: "Share the full contract address (0x...) and chain, and I will run the analysis and send you the dashboard."
      };
    }
    if (!chain || !SUPPORTED_CHAINS.has(chain)) {
      return {
        type: "single_reply",
        text: "I found a contract address. Which chain is it on? Supported: ethereum, polygon, bsc, arbitrum, optimism, base, avalanche."
      };
    }

    const ack = `Starting on-chain analysis for ${contract.slice(0, 8)}... on ${chain}. This usually takes 2-5 mins. I will post results shortly.`;
    const payload = await analyzeContract({ contractAddress: contract, chain });
    let finalReply = "";
    if (useLlm) {
      try {
        finalReply = safeTweetText(await draftOnchainReply(context, payload));
      } catch {
        finalReply = formatOnchainResult(payload);
      }
    } else {
      finalReply = formatOnchainResult(payload);
    }
    return {
      type: "ack_then_reply",
      ack,
      text: finalReply,
      conversationContract: contract,
      conversationChain: chain
    };
  }

  const fallbackContract = extractContractAddress(contextText);
  if (fallbackContract) {
    const fallbackChain = extractChain(contextText);
    if (!fallbackChain) {
      return {
        type: "single_reply",
        text: "I found a contract address. Which chain is it on? Supported: ethereum, polygon, bsc, arbitrum, optimism, base, avalanche."
      };
    }
    const ack = `Starting on-chain analysis for ${fallbackContract.slice(0, 8)}... on ${fallbackChain}. This usually takes 2-5 mins. I will post results shortly.`;
    const payload = await analyzeContract({ contractAddress: fallbackContract, chain: fallbackChain });
    const finalReply = useLlm ? safeTweetText(await draftOnchainReply(context, payload).catch(() => formatOnchainResult(payload))) : formatOnchainResult(payload);
    return {
      type: "ack_then_reply",
      ack,
      text: finalReply,
      conversationContract: fallbackContract,
      conversationChain: fallbackChain
    };
  }

  if (conversation.contract && conversation.chain && isRetryRequest(mentionText)) {
    const ack = `Starting on-chain analysis for ${conversation.contract.slice(0, 8)}... on ${conversation.chain}. This usually takes 2-5 mins. I will post results shortly.`;
    const payload = await analyzeContract({ contractAddress: conversation.contract, chain: conversation.chain });
    const finalReply = useLlm ? safeTweetText(await draftOnchainReply(context, payload).catch(() => formatOnchainResult(payload))) : formatOnchainResult(payload);
    return {
      type: "ack_then_reply",
      ack,
      text: finalReply,
      conversationContract: conversation.contract,
      conversationChain: conversation.chain
    };
  }

  if (useLlm) {
    const cooldownSeconds = Number(config.generalReplyCooldownSeconds || 600);
    const maxRegens = Number(config.generalReplyMaxRegenAttempts || 1);
    const now = Math.floor(Date.now() / 1000);
    const withinCooldown = recentReply && (now - Number(recentReply.lastTimestamp || 0) < cooldownSeconds);
    const repeatedSocialPing = Boolean(
      withinCooldown &&
      ["greeting", "intro"].includes(socialHint) &&
      (recentReply.lastSocialHint === socialHint || recentReply.lastMentionHash === mentionHash)
    );

    let avoidText = recentReply?.lastText || "";
    for (let attempt = 0; attempt <= maxRegens; attempt += 1) {
      const reply = safeTweetText(await draftGeneralReply({
        ...context,
        recentInteractionHint: recentReply ? "User has interacted recently. Acknowledge continuity naturally if it fits." : ""
      }, persona, attempt > 0 ? avoidText : ""));
      if (!reply) {
        continue;
      }
      const replyHash = hashText(reply);
      if (recentReply?.lastTextHash && replyHash === recentReply.lastTextHash && attempt < maxRegens) {
        continue;
      }
      if (repeatedSocialPing && recentReply?.lastTextHash && replyHash === recentReply.lastTextHash) {
        return { type: "skip" };
      }
      return {
        type: "single_reply",
        text: reply,
        generalReplyRecord: {
          lastText: reply,
          lastTextHash: replyHash,
          lastMentionHash: mentionHash,
          lastSocialHint: socialHint
        }
      };
    }
  }

  return {
    type: "single_reply",
    text: "Hey! On-Chain Wizard here. I can chat and help break down any EVM contract. Share address + chain and I will take it from there."
  };
}
