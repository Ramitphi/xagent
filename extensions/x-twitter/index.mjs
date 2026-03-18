import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildReplyPlan } from "./lib/router.mjs";
import { StateStore } from "./lib/state-store.mjs";
import { TwitterApi } from "./lib/twitter-api.mjs";
import { safeTweetText, splitTweetChunks } from "./lib/utils.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, "..", "..");

function readConfig(api) {
  return api.getConfig?.() || api.config || {};
}

function channelConfig(api) {
  const cfg = readConfig(api);
  return cfg.channels?.["x-twitter"] || {};
}

async function postThread(apiClient, text, inReplyToTweetId) {
  const ids = [];
  let anchor = inReplyToTweetId;
  for (const chunk of splitTweetChunks(text)) {
    const id = await apiClient.postReply(chunk, anchor);
    if (id) {
      ids.push(id);
      anchor = id;
    }
  }
  return ids;
}

async function pollOnce(api, runtime) {
  const cfg = channelConfig(api);
  if (!cfg.enabled) {
    return;
  }

  const stateStore = new StateStore(cfg);
  const state = await stateStore.load();
  const processedIds = new Set(Array.isArray(state.processedMentionIds) ? state.processedMentionIds.map(String) : []);
  const twitter = new TwitterApi(cfg.botUserId);
  const mentions = await twitter.fetchMentions({
    sinceId: state.lastSeenId || undefined,
    maxResults: Number(cfg.maxMentionsPerPoll || 10)
  });

  if (!mentions.length) {
    return;
  }

  mentions.sort((a, b) => Number(a.id) - Number(b.id));
  if (!state.lastSeenId && cfg.skipExistingOnStartup && !state.startupSynced) {
    state.lastSeenId = mentions[mentions.length - 1].id;
    state.startupSynced = true;
    await stateStore.save(state);
    api.logger?.info?.(`x-twitter startup sync: skipped ${mentions.length} mention(s)`);
    return;
  }

  for (const mention of mentions) {
    try {
      if (processedIds.has(mention.id)) {
        continue;
      }
      if (mention.authorId && String(mention.authorId) === String(cfg.botUserId)) {
        continue;
      }

      const parentText = mention.replyToTweetId ? await twitter.fetchTweetText(mention.replyToTweetId).catch(() => "") : "";
      const plan = await buildReplyPlan({
        mention: {
          ...mention,
          parentText,
          authorUsername: ""
        },
        state: {
          conversationContexts: state.conversationContexts || {},
          recentGeneralRepliesByUser: state.recentGeneralRepliesByUser || {}
        },
        config: cfg,
        rootDir: ROOT_DIR
      });

      if (plan.type === "skip") {
        continue;
      }

      if (plan.type === "ack_then_reply") {
        const ackIds = await postThread(twitter, safeTweetText(plan.ack), mention.id);
        const anchor = ackIds.at(-1) || mention.id;
        await postThread(twitter, safeTweetText(plan.text), anchor);
        state.conversationContexts = state.conversationContexts || {};
        if (mention.conversationId && plan.conversationState) {
          state.conversationContexts[mention.conversationId] = {
            contract: plan.conversationState.contract,
            chain: plan.conversationState.chain
          };
        }
      } else if (plan.type === "single_reply" && plan.text) {
        await postThread(twitter, safeTweetText(plan.text), mention.id);
        state.conversationContexts = state.conversationContexts || {};
        if (mention.conversationId && plan.conversationState) {
          state.conversationContexts[mention.conversationId] = {
            contract: plan.conversationState.contract,
            chain: plan.conversationState.chain
          };
        }
        if (plan.generalReplyRecord && mention.authorId) {
          state.recentGeneralRepliesByUser = state.recentGeneralRepliesByUser || {};
          state.recentGeneralRepliesByUser[mention.authorId] = {
            ...plan.generalReplyRecord,
            lastTimestamp: Math.floor(Date.now() / 1000)
          };
        }
      }
    } catch (error) {
      api.logger?.error?.(`x-twitter mention processing failed for ${mention.id}: ${error?.message || error}`);
    } finally {
      state.lastSeenId = mention.id;
      state.processedMentionIds = Array.isArray(state.processedMentionIds) ? state.processedMentionIds : [];
      state.processedMentionIds.push(String(mention.id));
      const maxSize = Math.max(100, Number(cfg.processedMentionsCacheSize || 2000));
      if (state.processedMentionIds.length > maxSize) {
        state.processedMentionIds = state.processedMentionIds.slice(-maxSize);
      }
      await stateStore.save(state);
    }
  }
}

const xTwitterChannel = {
  id: "x-twitter",
  meta: {
    id: "x-twitter",
    label: "X (Twitter)",
    selectionLabel: "X (Twitter)",
    docsPath: "/channels/x-twitter",
    blurb: "Official X mention polling and threaded replies.",
    aliases: ["x", "twitter"]
  },
  capabilities: {
    chatTypes: ["group", "direct"]
  },
  config: {
    listAccountIds: () => ["default"],
    resolveAccount: (cfg) => cfg.channels?.["x-twitter"] || {}
  },
  outbound: {
    deliveryMode: "thread",
    sendText: async ({ text, target, config }) => {
      const twitter = new TwitterApi(config?.channels?.["x-twitter"]?.botUserId);
      const tweetId = String(target || "").replace(/^tweet:/, "");
      const ids = await postThread(twitter, text, tweetId);
      return { ok: ids.length > 0, ids };
    }
  }
};

export default function register(api) {
  let timer = null;

  api.registerChannel({ plugin: xTwitterChannel });

  api.registerCommand({
    name: "xstatus",
    description: "Show x-twitter channel status",
    requireAuth: true,
    handler: async () => {
      const cfg = channelConfig(api);
      const stateStore = new StateStore(cfg);
      const state = await stateStore.load();
      return {
        text: JSON.stringify({
          enabled: Boolean(cfg.enabled),
          botUserId: cfg.botUserId || null,
          lastSeenId: state.lastSeenId || null,
          startupSynced: Boolean(state.startupSynced)
        })
      };
    }
  });

  api.registerService({
    id: "x-twitter-poller",
    start: async () => {
      const cfg = channelConfig(api);
      if (!cfg.enabled) {
        api.logger?.info?.("x-twitter service disabled");
        return;
      }
      await pollOnce(api).catch((error) => {
        api.logger?.error?.(`x-twitter initial poll failed: ${error?.message || error}`);
      });
      const intervalMs = Math.max(15, Number(cfg.pollIntervalSeconds || 60)) * 1000;
      timer = setInterval(() => {
        pollOnce(api).catch((error) => {
          api.logger?.error?.(`x-twitter poll failed: ${error?.message || error}`);
        });
      }, intervalMs);
      api.logger?.info?.(`x-twitter poller started with interval ${intervalMs}ms`);
    },
    stop: async () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }
  });
}
