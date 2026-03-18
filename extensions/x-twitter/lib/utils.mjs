export const SUPPORTED_CHAINS = new Set([
  "ethereum",
  "polygon",
  "bsc",
  "arbitrum",
  "optimism",
  "base",
  "avalanche"
]);

export const CONTRACT_RE = /0x[a-fA-F0-9]{40}/;
export const RETRY_RE = /\b(again|retry|try again|rerun|re-run|recheck|re-analy[sz]e)\b/i;
export const GREETING_RE = /\b(hi|hello|hey|gm|good morning|yo|hola)\b/i;
export const INTRO_RE = /\b(introduce yourself|who are you|about you|what do you do)\b/i;
export const SELF_HANDLE_RE = /@OWAIbot\b/gi;

const CHAIN_PATTERNS = {
  ethereum: [/\beth(?:ereum)?\b/i, /\bmainnet\b/i],
  polygon: [/\bpolygon\b/i, /\bmatic\b/i],
  bsc: [/\bbsc\b/i, /\bbinance smart chain\b/i],
  arbitrum: [/\barbitrum\b/i, /\barb\b/i],
  optimism: [/\boptimism\b/i, /\bop mainnet\b/i],
  base: [/\bon\s+base\b/i, /\bbase\s+chain\b/i, /\b#base\b/i],
  avalanche: [/\bavalanche\b/i, /\bavax\b/i]
};

export function socialIntentHint(text) {
  if (INTRO_RE.test(text)) {
    return "intro";
  }
  if (GREETING_RE.test(text)) {
    return "greeting";
  }
  return "general";
}

export function extractContractAddress(text) {
  return text.match(CONTRACT_RE)?.[0] ?? null;
}

export function extractChain(text) {
  for (const [chain, patterns] of Object.entries(CHAIN_PATTERNS)) {
    if (patterns.some((pattern) => pattern.test(text))) {
      return chain;
    }
  }
  return null;
}

export function isValidContract(value) {
  return CONTRACT_RE.test(value) && value.length === 42;
}

export function isRetryRequest(text) {
  return RETRY_RE.test(text);
}

export function safeTweetText(text) {
  return String(text).replace(SELF_HANDLE_RE, "").replace(/\s+/g, " ").trim();
}

export function splitTweetChunks(text, maxLength = 280) {
  const cleaned = safeTweetText(text);
  if (cleaned.length <= maxLength) {
    return cleaned ? [cleaned] : [];
  }

  const chunks = [];
  let remaining = cleaned;
  while (remaining.length > maxLength) {
    let cut = remaining.lastIndexOf(" ", maxLength);
    if (cut < Math.floor(maxLength * 0.6)) {
      cut = maxLength;
    }
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) {
    chunks.push(remaining);
  }
  return chunks;
}

export function hashText(text) {
  return Array.from(text).reduce((acc, char) => ((acc * 31) + char.charCodeAt(0)) >>> 0, 7).toString(16);
}
