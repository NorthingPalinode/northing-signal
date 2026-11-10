import { useEffect, useRef } from "react";

const paths: Record<string, string> = {
  follow: "M12 21s-9-5.5-9-12a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6.5-9 12-9 12Z",
  home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  compass: "m16 8-3 5-5 3 3-5Z M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  book: "M12 6c-3-3-7-3-10-2v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-3-1-7-1-10 2v15",
  refresh: "M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 14 6 M18 18A8 8 0 0 1 4 12",
  search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  arrow: "M5 12h14 m-6-6 6 6-6 6",
  back: "M19 12H5 m6-6-6 6 6 6",
  close: "m6 6 12 12 M6 18 18 6",
  settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  bookmark: "M6 3h12v18l-6-4-6 4Z",
  check: "m5 12 4 4 10-10",
  external: "M14 3h7v7 m0-7-11 11 M10 3H3v18h18v-7",
  clock: "M12 7v5l4 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  more: "M5 12h.01 M12 12h.01 M19 12h.01",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  signal: "M4 20v-4 M10 20v-8 M16 20V8 M22 20V4",
  thumb: "M7 10v11 M7 10l4-8a3 3 0 0 1 3 3v4h5a2 2 0 0 1 2 2l-2 8a2 2 0 0 1-2 2H7",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  minus: "M5 12h14 M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18",
  plus: "M12 5v14 M5 12h14",
  pause: "M9 5v14 M15 5v14",
  play: "m7 4 13 8-13 8Z",
  trash: "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13",
  edit: "M4 20h4L19 9l-4-4L4 16Z",
};

export function Glyph({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3 : 1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.compass} />
    </svg>
  );
}

/**
 * Modal surface. `side` slides in from the right on desktop (reading panels);
 * every variant becomes a full-height bottom sheet on phones.
 */
export function Sheet({
  title,
  close,
  children,
  variant = "center",
  footer,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
  variant?: "center" | "wide" | "side";
  footer?: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = ref.current;
    node?.showModal();
    document.documentElement.classList.add("r-locked");
    return () => {
      node?.close();
      document.documentElement.classList.remove("r-locked");
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className={"r-sheet r-sheet-" + variant}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="r-sheet-panel">
        <header className="r-sheet-head">
          <span>{title}</span>
          <button className="r-icon" aria-label="关闭" onClick={close}>
            <Glyph name="close" size={18} />
          </button>
        </header>
        <div className="r-sheet-body">{children}</div>
        {footer && <footer className="r-sheet-foot">{footer}</footer>}
      </div>
    </dialog>
  );
}

/** Small transient confirmation pinned to the bottom of the viewport. */
export function Toast({
  message,
  action,
  dismiss,
}: {
  message: string;
  action?: { label: string; run: () => void };
  dismiss: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(dismiss, 5000);
    return () => clearTimeout(timer);
  }, [message, dismiss]);
  return (
    <div className="r-toast" role="status">
      <span>{message}</span>
      {action && (
        <button
          onClick={() => {
            action.run();
            dismiss();
          }}
        >
          {action.label}
        </button>
      )}
      <button className="r-icon" aria-label="关闭提示" onClick={dismiss}>
        <Glyph name="close" size={15} />
      </button>
    </div>
  );
}
