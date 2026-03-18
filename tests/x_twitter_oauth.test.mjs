import test from "node:test";
import assert from "node:assert/strict";

import { buildOAuthHeader } from "../extensions/x-twitter/lib/oauth.mjs";

test("oauth header omits JSON body fields from signature when requested", () => {
  const baseArgs = {
    method: "POST",
    url: "https://api.twitter.com/2/tweets",
    query: {},
    body: {
      text: "hello world",
      reply: {
        in_reply_to_tweet_id: "123"
      }
    },
    consumerKey: "consumer-key",
    consumerSecret: "consumer-secret",
    accessToken: "access-token",
    accessTokenSecret: "access-token-secret"
  };

  const withBody = buildOAuthHeader(baseArgs);
  const withoutBody = buildOAuthHeader({
    ...baseArgs,
    includeBodyInSignature: false
  });

  assert.notEqual(withBody, withoutBody);
});

