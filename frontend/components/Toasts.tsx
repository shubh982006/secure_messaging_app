"use client";

import { useStore } from "@/lib/store";

/** Signal's toast: a dark pill that slides up from the bottom of the pane. */
export function Toasts() {
  const toasts = useStore((state) => state.toasts);
  const dismiss = useStore((state) => state.dismissToast);

  if (!toasts.length) return null;

  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[60] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          onClick={() => dismiss(toast.id)}
          className="animate-fade-up pointer-events-auto max-w-[min(90vw,420px)] rounded-lg px-4 py-3 text-left text-[14px] shadow-lg"
          style={{
            background: "var(--sig-elevated)",
            color: toast.tone === "error" ? "var(--color-sig-danger)" : "var(--sig-text)",
            border: "1px solid var(--sig-border)",
            boxShadow: "var(--sig-shadow)",
          }}
        >
          {toast.text}
        </button>
      ))}
    </div>
  );
}
