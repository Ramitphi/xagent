import { buildOAuthHeader } from "./oauth.mjs";

const API_BASE = "https://api.twitter.com";

async function requestJson({ method, path, query = {}, body, credentials }) {
  const url = new URL(`${API_BASE}${path}`);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  }

  const header = buildOAuthHeader({
    method,
    url: `${API_BASE}${path}`,
    query,
    body: body && typeof body === "object" ? body : {},
    consumerKey: credentials.consumerKey,
    consumerSecret: credentials.consumerSecret,
    accessToken: credentials.accessToken,
    accessTokenSecret: credentials.accessTokenSecret
  });

  const response = await fetch(url, {
    method,
    headers: {
      "Authorization": header,
      "Content-Type": "application/json"
    },
    body: body ? JSON.stringify(body) : undefined
  });

  if (!response.ok) {
    const text = await response.text();
    const error = new Error(`${method} ${path} failed: ${response.status} ${text}`);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export class TwitterApi {
  constructor(botUserId) {
    this.credentials = {
      consumerKey: process.env.X_API_KEY,
      consumerSecret: process.env.X_API_KEY_SECRET,
      accessToken: process.env.X_ACCESS_TOKEN,
      accessTokenSecret: process.env.X_ACCESS_TOKEN_SECRET
    };
    this.botUserId = botUserId;
  }

  validateCredentials() {
    for (const key of ["consumerKey", "consumerSecret", "accessToken", "accessTokenSecret"]) {
      if (!this.credentials[key]) {
        throw new Error(`Missing required X credential: ${key}`);
      }
    }
  }

  async fetchMentions({ sinceId, maxResults }) {
    this.validateCredentials();
    const data = await requestJson({
      method: "GET",
      path: `/2/users/${this.botUserId}/mentions`,
      query: {
        since_id: sinceId || undefined,
        max_results: Math.max(5, Math.min(maxResults, 100)),
        "tweet.fields": "author_id,created_at,conversation_id,referenced_tweets"
      },
      credentials: this.credentials
    });

    return (data?.data || []).map((tweet) => {
      const replyTo = Array.isArray(tweet.referenced_tweets)
        ? tweet.referenced_tweets.find((item) => item.type === "replied_to")?.id || null
        : null;
      return {
        id: String(tweet.id),
        text: tweet.text,
        authorId: tweet.author_id ? String(tweet.author_id) : null,
        conversationId: tweet.conversation_id ? String(tweet.conversation_id) : null,
        replyToTweetId: replyTo ? String(replyTo) : null
      };
    });
  }

  async fetchTweetText(tweetId) {
    this.validateCredentials();
    const data = await requestJson({
      method: "GET",
      path: `/2/tweets/${tweetId}`,
      query: {
        "tweet.fields": "text"
      },
      credentials: this.credentials
    });
    return data?.data?.text || null;
  }

  async postReply(text, inReplyToTweetId) {
    this.validateCredentials();
    try {
      const data = await requestJson({
        method: "POST",
        path: "/2/tweets",
        body: {
          text,
          reply: {
            in_reply_to_tweet_id: inReplyToTweetId
          }
        },
        credentials: this.credentials
      });
      return data?.data?.id ? String(data.data.id) : "";
    } catch (error) {
      if (String(error.message || "").toLowerCase().includes("duplicate")) {
        return "";
      }
      throw error;
    }
  }

  async getMe() {
    this.validateCredentials();
    const data = await requestJson({
      method: "GET",
      path: "/2/users/me",
      credentials: this.credentials
    });
    return data?.data || null;
  }
}
