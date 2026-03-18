import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

function defaultStateFile(config) {
  const root = config.stateDir || process.env.OPENCLAW_STATE_DIR || path.join(os.homedir(), ".openclaw", "state");
  return path.join(root, "x-twitter-state.json");
}

export class StateStore {
  constructor(config) {
    this.path = defaultStateFile(config);
  }

  async load() {
    try {
      const raw = await fs.readFile(this.path, "utf8");
      return JSON.parse(raw);
    } catch (error) {
      if (error && error.code === "ENOENT") {
        return { lastSeenId: null, startupSynced: false };
      }
      throw error;
    }
  }

  async save(state) {
    await fs.mkdir(path.dirname(this.path), { recursive: true });
    await fs.writeFile(this.path, JSON.stringify(state, null, 2));
  }
}
