// Account labels shown in the menu (2026-11-23).
import { test } from "node:test";
import assert from "node:assert/strict";
import { OFFLINE, accountLabel, failureMessage, quotaLabel, reach, type Account } from "../src/auth.ts";

const account = (changes: Partial<Account> = {}): Account => ({
  id: "3f2a9c1b8d7e6f50",
  role: "user",
  auth: "token",
  limits: { follows: 3, requests_per_day: 10, requests_today: 4 },
  ...changes,
});

test("accounts show their role and a short id, never a token", () => {
  assert.equal(accountLabel(account()), "读者 · 3f2a9c");
  assert.equal(accountLabel(account({ role: "admin" })), "管理员 · 3f2a9c");
});

test("only limited accounts show a daily quota", () => {
  assert.equal(quotaLabel(account()), "今天已用 4 / 10 次主动检索与 AI 理解");
  const admin = account({ role: "admin", limits: { follows: 12, requests_per_day: null, requests_today: 7 } });
  assert.equal(quotaLabel(admin), null);
});

test("a stopped server reads as unreachable, not as a vague failure (2026-11-24)", async () => {
  assert.equal(failureMessage(429, { detail: "今天的额度已用完" }), "今天的额度已用完");
  assert.equal(failureMessage(502, {}), OFFLINE); // Cloudflare or a gateway with no server behind it
  assert.equal(failureMessage(530, null), OFFLINE);
  assert.equal(failureMessage(500, {}), "暂时无法完成，请重试。");
  assert.equal(failureMessage(422, {}, "方案内容不完整"), "方案内容不完整");
  const original = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  try {
    await assert.rejects(reach("/api/reader"), { message: OFFLINE });
  } finally {
    globalThis.fetch = original;
  }
});
