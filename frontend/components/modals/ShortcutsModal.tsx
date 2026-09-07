"use client";

import { Modal } from "@/components/Modal";

export const SHORTCUT_GROUPS: {
  title: string;
  items: { keys: string[]; label: string }[];
}[] = [
  {
    title: "Navigation",
    items: [
      { keys: ["mod", "K"], label: "Search chats" },
      { keys: ["Alt", "↑"], label: "Previous chat" },
      { keys: ["Alt", "↓"], label: "Next chat" },
      { keys: ["Esc"], label: "Close, clear search, or cancel a reply" },
    ],
  },
  {
    title: "Chats",
    items: [
      { keys: ["mod", "N"], label: "New chat" },
      { keys: ["mod", "Shift", "N"], label: "New group" },
      { keys: ["mod", "F"], label: "Search in this conversation" },
      { keys: ["mod", "I"], label: "Conversation info" },
    ],
  },
  {
    title: "Composing",
    items: [
      { keys: ["Enter"], label: "Send" },
      { keys: ["Shift", "Enter"], label: "New line" },
      { keys: ["mod", "V"], label: "Paste an image to attach it" },
    ],
  },
  {
    title: "Application",
    items: [
      { keys: ["mod", ","], label: "Settings" },
      { keys: ["mod", "Shift", "D"], label: "Toggle dark / light theme" },
      { keys: ["?"], label: "Show this help" },
    ],
  },
];

/** `mod` renders as ⌘ on Apple platforms and Ctrl elsewhere. */
export function modKeyLabel(): string {
  if (typeof navigator === "undefined") return "Ctrl";
  return /Mac|iPhone|iPad/.test(navigator.platform ?? navigator.userAgent) ? "⌘" : "Ctrl";
}

export function ShortcutsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const mod = modKeyLabel();

  return (
    <Modal open={open} title="Keyboard shortcuts" onClose={onClose} width={460}>
      {SHORTCUT_GROUPS.map((group) => (
        <section key={group.title} className="mb-5">
          <h3 className="mb-2 text-[12px] font-medium uppercase tracking-wider text-sig-text-3">
            {group.title}
          </h3>
          <div className="space-y-1">
            {group.items.map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between gap-4 rounded-lg px-2 py-1.5"
              >
                <span className="text-[14px] text-sig-text">{item.label}</span>
                <span className="flex shrink-0 items-center gap-1">
                  {item.keys.map((key) => (
                    <kbd
                      key={key}
                      className="min-w-[26px] rounded border px-1.5 py-0.5 text-center text-[11.5px] font-medium text-sig-text-2"
                      style={{
                        background: "var(--sig-hover)",
                        borderColor: "var(--sig-border)",
                      }}
                    >
                      {key === "mod" ? mod : key}
                    </kbd>
                  ))}
                </span>
              </div>
            ))}
          </div>
        </section>
      ))}
    </Modal>
  );
}
