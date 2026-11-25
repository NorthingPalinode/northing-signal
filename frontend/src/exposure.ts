import { useEffect, useRef } from "react";
import type { Story } from "./reader/types";

/** Sends a one-off "shown" interaction the first time a story is on screen. */
export function useExposure(
  story: Story,
  send: (s: Story, kind: string) => Promise<unknown>,
) {
  const ref = useRef<HTMLElement>(null);
  const sent = useRef(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const check = () => {
      const box = node.getBoundingClientRect();
      if (
        !sent.current &&
        document.visibilityState === "visible" &&
        box.bottom > 0 &&
        box.top < innerHeight &&
        box.height > 0
      ) {
        sent.current = true;
        void send(story, "shown").catch(() => {
          sent.current = false;
        });
      }
    };
    const observer = new IntersectionObserver(check, { threshold: 0.25 });
    observer.observe(node);
    document.addEventListener("visibilitychange", check);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", check);
    };
  }, [story.id, story.version, send]);
  return ref;
}
