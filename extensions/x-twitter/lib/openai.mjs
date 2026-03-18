const DEFAULT_MODEL = process.env.OPENAI_MODEL || "gpt-4.1-mini";
const DEFAULT_TIMEOUT_MS = Number(process.env.LLM_TIMEOUT_SECONDS || process.env.REQUEST_TIMEOUT_SECONDS || "20") * 1000;

async function chat({ system, user }) {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is not set");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: DEFAULT_MODEL,
        temperature: 0,
        messages: [
          { role: "system", content: system },
          { role: "user", content: user }
        ]
      }),
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`OpenAI error ${response.status}: ${await response.text()}`);
    }

    const data = await response.json();
    const content = data?.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error("OpenAI returned empty content");
    }
    return String(content);
  } finally {
    clearTimeout(timeout);
  }
}

export async function classifyMention(context) {
  const merged = `MENTION:\n${context.mentionText}\n\nPARENT:\n${context.parentText}`.slice(0, 4000);
  const text = await chat({
    system: "You are a precise assistant. Follow the output format exactly. Do not provide financial advice.",
    user: [
      "Classify if this tweet context is asking for EVM smart-contract onchain analysis.",
      "Allowed chains: ethereum, polygon, bsc, arbitrum, optimism, base, avalanche.",
      "If uncertain, confidence must be low.",
      "",
      "Return EXACTLY 5 lines with this format:",
      "INTENT: onchain_analysis|general",
      "CONTRACT: <0x... or NONE>",
      "CHAIN: <ethereum|polygon|bsc|arbitrum|optimism|base|avalanche|NONE>",
      "CONFIDENCE: <0.00-1.00>",
      "RATIONALE: <short reason>",
      "",
      `Context:\n${merged}`
    ].join("\n")
  });

  const fields = {
    intent: "general",
    contract: null,
    chain: null,
    confidence: 0,
    rationale: ""
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line.includes(":")) {
      continue;
    }
    const [rawKey, ...rest] = line.split(":");
    const key = rawKey.trim().toLowerCase();
    const value = rest.join(":").trim();
    if (key === "intent" && value) {
      fields.intent = value.toLowerCase();
    } else if (key === "contract") {
      fields.contract = value.toUpperCase() === "NONE" ? null : value;
    } else if (key === "chain") {
      fields.chain = value.toLowerCase() === "none" ? null : value.toLowerCase();
    } else if (key === "confidence") {
      const parsed = Number(value);
      fields.confidence = Number.isFinite(parsed) ? Math.max(0, Math.min(1, parsed)) : 0;
    } else if (key === "rationale") {
      fields.rationale = value;
    }
  }

  return fields;
}

export async function draftGeneralReply(context, persona, avoidText = "") {
  const variationRule = avoidText
    ? `Do not reuse this prior reply wording: ${avoidText.slice(0, 400)}. Use different sentence structure while keeping meaning.`
    : "";

  const prompt = [
    "Write one reply tweet to a mention on X.",
    "Always reply to greetings and self-introduction requests.",
    "Be human, warm, concise, and factual.",
    "Use varied openings, avoid robotic repetition, and sound like a real person.",
    "No financial promises. No fabricated onchain data. Do not include stack traces or internal errors.",
    "",
    "Persona instructions:",
    persona.slice(0, 3000),
    "",
    "If social intent is intro: introduce yourself as On-Chain Wizard, mention what you can do, and end with a clear CTA.",
    "If social intent is greeting: give a warm hello and offer help in one or two lines.",
    "If social intent is general: answer the user's current line first, then mention capabilities if useful.",
    "Style exemplar (do not copy verbatim): \"Hi there! On-Chain Wizard here, ready to help you analyze any EVM smart contract. Share a contract address + chain and I’ll take it from there.\"",
    `Mention author username: ${context.authorUsername || ""}`,
    `Mention text: ${context.mentionText.slice(0, 1200)}`,
    `Parent tweet text: ${context.parentText.slice(0, 1200)}`,
    `Social intent hint: ${context.socialHint || "general"}`,
    `Recent interaction hint: ${(context.recentInteractionHint || "").slice(0, 400)}`,
    variationRule
  ].join("\n");

  return (await chat({
    system: "You are a precise assistant. Follow the output format exactly. Do not provide financial advice.",
    user: prompt
  })).replace(/\s+/g, " ").trim();
}

export async function draftOnchainReply(context, payload) {
  const result = payload?.result || {};
  const dashboardUrl = result.dashboardUrl || payload.dashboardUrl || "";
  const prompt = [
    "Draft one X reply for this analysis result.",
    "Start with TLDR if available. Include dashboard URL if present.",
    "Mention one key method stat if available. Keep factual and concise.",
    "NEVER truncate, shorten, or ellipsize URLs. Always include the full dashboard URL exactly.",
    "No markdown, no hashtags unless already in source text, no financial advice.",
    "",
    `Original mention: ${String(context.mentionText || "").slice(0, 800)}`,
    `Analysis status: ${payload.status || ""}`,
    `Dashboard URL: ${dashboardUrl}`,
    `Analysis payload JSON: ${JSON.stringify(payload)}`
  ].join("\n");

  const text = (await chat({
    system: "You are a precise assistant. Follow the output format exactly. Do not provide financial advice.",
    user: prompt
  })).replace(/\s+/g, " ").trim();

  if (dashboardUrl && !text.includes(dashboardUrl)) {
    return `${text} Dashboard: ${dashboardUrl}`.trim();
  }
  return text;
}
