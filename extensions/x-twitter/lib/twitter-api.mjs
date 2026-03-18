import { TwitterApi as TwitterApiV2 } from "twitter-api-v2";

export class TwitterApi {
  constructor(botUserId) {
    this.credentials = {
      appKey: process.env.X_API_KEY,
      appSecret: process.env.X_API_KEY_SECRET,
      accessToken: process.env.X_ACCESS_TOKEN,
      accessSecret: process.env.X_ACCESS_TOKEN_SECRET
    };
    this.botUserId = botUserId;
    this.client = null;
  }

  validateCredentials() {
    for (const key of ["appKey", "appSecret", "accessToken", "accessSecret"]) {
      if (!this.credentials[key]) {
        throw new Error(`Missing required X credential: ${key}`);
      }
    }
  }

  getClient() {
    this.validateCredentials();
    if (!this.client) {
      this.client = new TwitterApiV2(this.credentials).readWrite;
    }
    return this.client;
  }

  async fetchMentions({ sinceId, maxResults }) {
    const client = this.getClient();
    const data = await client.v2.get(`users/${this.botUserId}/mentions`, {
      since_id: sinceId || undefined,
      max_results: Math.max(5, Math.min(maxResults, 100)),
      "tweet.fields": "author_id,created_at,conversation_id,referenced_tweets"
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
    const client = this.getClient();
    const data = await client.v2.get(`tweets/${tweetId}`, {
      "tweet.fields": "text"
    });
    return data?.data?.text || null;
  }

  async postReply(text, inReplyToTweetId) {
    const client = this.getClient();
    try {
      const data = await client.v2.post("tweets", {
        text,
        reply: {
          in_reply_to_tweet_id: inReplyToTweetId
        }
      });
      return data?.data?.id ? String(data.data.id) : "";
    } catch (error) {
      if (String(error?.message || "").toLowerCase().includes("duplicate")) {
        return "";
      }
      throw error;
    }
  }

  async getMe() {
    const client = this.getClient();
    const data = await client.v2.get("users/me");
    return data?.data || null;
  }
}
