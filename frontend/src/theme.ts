import { useCallback, useEffect, useState } from "react";

/** 浅色, 深色 or 跟随系统. Kept per device (a screen's setting, not the account's). */
export type ThemeChoice = "light" | "dark" | "auto";

const KEY = "ns-theme";
const BAR = { light: "#f6f6f3", dark: "#131417" };
const system = () => matchMedia("(prefers-color-scheme: dark)");

export function storedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

/** The palette a choice shows now (index.html applies the same rule before the first paint). */
export function resolveTheme(choice: ThemeChoice, systemDark: boolean): "light" | "dark" {
  return choice === "auto" ? (systemDark ? "dark" : "light") : choice;
}

function apply(choice: ThemeChoice) {
  const resolved = resolveTheme(choice, system().matches);
  const root = document.documentElement;
  if (root.dataset.theme === resolved) return;
  const swap = () => {
    root.dataset.theme = resolved;
    const bar = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (bar) bar.content = BAR[resolved];
  };
  // A short cross-fade where the browser has one; instant when motion is reduced.
  const fade = (document as Document & { startViewTransition?: (run: () => void) => unknown })
    .startViewTransition;
  if (fade && !matchMedia("(prefers-reduced-motion: reduce)").matches) fade.call(document, swap);
  else swap();
}

/** The reader's theme choice; 跟随系统 follows the system live, without a reload. */
export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme);
  useEffect(() => {
    apply(choice);
    if (choice !== "auto") return;
    const query = system();
    const follow = () => apply("auto");
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, [choice]);
  const set = useCallback((next: ThemeChoice) => {
    try {
      if (next === "auto") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the choice still applies until the page closes */
    }
    setChoice(next);
  }, []);
  return [choice, set];
}
