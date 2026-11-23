/** Accounts: one token per reader. The token lives in an HttpOnly cookie, never in page script. */

export type Account = {
  id: string;
  role: "admin" | "user";
  /** "off" on a personal install without accounts. */
  auth: "token" | "off";
  limits: {
    follows: number;
    requests_per_day: number | null;
    requests_today: number;
  };
};

export type Session = {
  auth: "token" | "off";
  signup: boolean;
  user: Account | null;
};

const SIGNED_OUT = "northing:signed-out";

/** Any API call answered 401 sends the reader back to the sign-in page. */
export function signedOut() {
  window.dispatchEvent(new Event(SIGNED_OUT));
}

export function onSignedOut(listener: () => void) {
  window.addEventListener(SIGNED_OUT, listener);
  return () => window.removeEventListener(SIGNED_OUT, listener);
}

export async function auth<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  const response = await fetch("/api/auth" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(typeof value.detail === "string" ? value.detail : "暂时无法完成，请重试。");
  return value;
}

/** Account line for the menu, e.g. "管理员 · 3f2a…" */
export function accountLabel(account: Account) {
  return `${account.role === "admin" ? "管理员" : "读者"} · ${account.id.slice(0, 6)}`;
}

/** "今天已用 3 / 10 次" — or null when the reader is not limited. */
export function quotaLabel(account: Account) {
  const { requests_per_day: limit, requests_today: used } = account.limits;
  return limit === null ? null : `今天已用 ${used} / ${limit} 次主动检索与 AI 理解`;
}
