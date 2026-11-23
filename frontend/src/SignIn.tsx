import { useState } from "react";
import { auth, type Account } from "./auth";
import { Glyph } from "./ui";
import brandMark from "./assets/brand.svg?no-inline";

/**
 * Sign in with a token, or create one. A new token is shown exactly once: the reader
 * confirms they kept it before entering, because nobody can recover it later.
 */
export default function SignIn({
  signup,
  enter,
}: {
  signup: boolean;
  enter: (account: Account) => void;
}) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{ token: string; user: Account } | null>(null);
  const [copied, setCopied] = useState(false);
  const [kept, setKept] = useState(false);

  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await auth<{ user: Account }>("/login", "POST", { token: token.trim() });
      enter(result.user);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    setError("");
    try {
      setCreated(await auth<{ token: string; user: Account }>("/register", "POST"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
    } catch {
      setError("无法自动复制，请手动选中令牌复制。");
    }
  }

  return (
    <main className="r-signin">
      <div className="r-signin-card">
        <div className="r-signin-brand">
          <img src={brandMark} alt="" width={36} height={36} />
          <div>
            <h1>Northing Signal</h1>
            <p>AI 发布、测试与更正的事件追踪阅读器</p>
          </div>
        </div>

        {created ? (
          <section aria-labelledby="new-token">
            <h2 id="new-token">这是你的令牌</h2>
            <p className="r-signin-lead">
              令牌就是你的账号：收藏、反馈、追踪话题和阅读偏好都跟着它走。
              <strong>它只显示这一次，丢失后无法找回。</strong>
              请复制保存到密码管理器或备忘录，在其他设备上用它登录。
            </p>
            <div className="r-token-box">
              <code aria-label="你的令牌">{created.token}</code>
              <button className="r-button" type="button" onClick={() => void copy()}>
                <Glyph name={copied ? "check" : "copy"} size={16} />
                {copied ? "已复制" : "复制"}
              </button>
            </div>
            <label className="r-signin-check">
              <input type="checkbox" checked={kept} onChange={(e) => setKept(e.target.checked)} />
              我已保存好这个令牌
            </label>
            <button
              className="r-button primary block"
              type="button"
              disabled={!kept}
              onClick={() => enter(created.user)}
            >
              开始阅读
            </button>
          </section>
        ) : (
          <>
            <form onSubmit={(e) => void signIn(e)}>
              <label className="r-signin-label" htmlFor="token">
                用令牌登录
              </label>
              <input
                id="token"
                className="r-signin-input"
                type="password"
                autoComplete="current-password"
                spellCheck={false}
                placeholder="nst_…"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="r-button primary block" type="submit" disabled={busy || !token.trim()}>
                {busy ? "请稍候…" : "登录"}
              </button>
            </form>
            {signup ? (
              <div className="r-signin-new">
                <span>还没有令牌？</span>
                <button className="r-button block" type="button" disabled={busy} onClick={() => void create()}>
                  一键创建令牌
                </button>
                <small>不需要邮箱或手机号。每个令牌是一个独立账号，有自己的收藏、反馈和追踪。</small>
              </div>
            ) : (
              <p className="r-signin-lead">本站暂未开放创建令牌，请向管理员索取。</p>
            )}
          </>
        )}
        {error && (
          <p className="r-signin-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
