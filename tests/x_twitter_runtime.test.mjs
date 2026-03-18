import test from "node:test";
import assert from "node:assert/strict";

import { safeTweetText } from "../extensions/x-twitter/lib/utils.mjs";

test("safeTweetText strips self-handle and normalizes whitespace", () => {
  assert.equal(
    safeTweetText("Hey @OWAIbot   there"),
    "Hey there"
  );
});
