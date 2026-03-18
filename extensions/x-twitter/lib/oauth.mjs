import crypto from "node:crypto";

function percentEncode(value) {
  return encodeURIComponent(value)
    .replace(/[!'()*]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`);
}

function normalizeParams(params) {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null)
    .flatMap(([key, value]) => {
      if (Array.isArray(value)) {
        return value.map((item) => [percentEncode(key), percentEncode(String(item))]);
      }
      return [[percentEncode(key), percentEncode(String(value))]];
    })
    .sort(([keyA, valueA], [keyB, valueB]) => {
      if (keyA === keyB) {
        return valueA.localeCompare(valueB);
      }
      return keyA.localeCompare(keyB);
    })
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
}

function nonce() {
  return crypto.randomBytes(16).toString("hex");
}

export function buildOAuthHeader({
  method,
  url,
  query = {},
  body = {},
  rawBody = "",
  includeBodyInSignature = true,
  consumerKey,
  consumerSecret,
  accessToken,
  accessTokenSecret
}) {
  const oauthParams = {
    oauth_consumer_key: consumerKey,
    oauth_nonce: nonce(),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
    oauth_token: accessToken,
    oauth_version: "1.0"
  };

  if (!includeBodyInSignature && rawBody) {
    oauthParams.oauth_body_hash = crypto.createHash("sha1").update(rawBody).digest("base64");
  }

  const allParams = {
    ...query,
    ...(includeBodyInSignature ? body : {}),
    ...oauthParams
  };

  const baseString = [
    method.toUpperCase(),
    percentEncode(url),
    percentEncode(normalizeParams(allParams))
  ].join("&");

  const signingKey = `${percentEncode(consumerSecret)}&${percentEncode(accessTokenSecret)}`;
  const signature = crypto.createHmac("sha1", signingKey).update(baseString).digest("base64");

  const headerParams = {
    ...oauthParams,
    oauth_signature: signature
  };

  const headerValue = Object.entries(headerParams)
    .sort(([keyA], [keyB]) => keyA.localeCompare(keyB))
    .map(([key, value]) => `${percentEncode(key)}="${percentEncode(String(value))}"`)
    .join(", ");

  return `OAuth ${headerValue}`;
}
