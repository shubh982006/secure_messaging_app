"use client";

import { useEffect } from "react";

export interface ShortcutHandlers {
  onSearch: () => void;
  onNewChat: () => void;
  onNewGroup: () => void;
  onSettings: () => void;
  onInfo: () => void;
  onToggleTheme: () => void;
  onHelp: () => void;
  onEscape: () => void;
  onMoveConversation: (direction: 1 | -1) => void;
}

/** True when the user is typing somewhere a shortcut must not hijack. */
function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element) return false;
  const tag = element.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    element.isContentEditable
  );
}

/**
 * Global keyboard shortcuts.
 *
 * Modifier combinations work everywhere (including while composing, because
 * Cmd+K should still open search mid-sentence). Bare keys like `?` only fire
 * when focus is not in a text field, so typing a question mark still works.
 */
export function useKeyboardShortcuts(handlers: ShortcutHandlers, enabled = true) {
  useEffect(() => {
    if (!enabled) return;

    const onKey = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key;
      const lower = key.toLowerCase();

      if (key === "Escape") {
        handlers.onEscape();
        return;
      }

      if (mod && event.shiftKey && lower === "n") {
        event.preventDefault();
        handlers.onNewGroup();
        return;
      }
      if (mod && event.shiftKey && lower === "d") {
        event.preventDefault();
        handlers.onToggleTheme();
        return;
      }
      if (mod && !event.shiftKey) {
        if (lower === "k") {
          event.preventDefault();
          handlers.onSearch();
          return;
        }
        if (lower === "n") {
          event.preventDefault();
          handlers.onNewChat();
          return;
        }
        if (lower === "i") {
          event.preventDefault();
          handlers.onInfo();
          return;
        }
        if (key === ",") {
          event.preventDefault();
          handlers.onSettings();
          return;
        }
      }

      // Alt+Arrow walks the conversation list without leaving the keyboard.
      if (event.altKey && (key === "ArrowDown" || key === "ArrowUp")) {
        event.preventDefault();
        handlers.onMoveConversation(key === "ArrowDown" ? 1 : -1);
        return;
      }

      if (!mod && !event.altKey && key === "?" && !isTypingTarget(event.target)) {
        event.preventDefault();
        handlers.onHelp();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlers, enabled]);
}
