// Pure UI helper checks. Node 24's built-in TS transform; no added dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import { searchSources, sourceName } from "../src/searchSources.ts";

test("every search channel has a display name", () => {
  for (const [key, label] of Object.entries(searchSources)) {
    assert.ok(label.trim(), key);
    assert.equal(sourceName(key), label);
  }
});

test("unknown channels fall back to their raw id", () => {
  assert.equal(sourceName("future-channel"), "future-channel");
});
