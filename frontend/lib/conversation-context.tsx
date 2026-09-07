"use client";

import { createContext, useContext } from "react";

/** Lets the chat pane open the info modal that the shell owns. */
export const ConversationContext = createContext<{ openInfo: () => void }>({
  openInfo: () => {},
});

export function useConversationShell() {
  return useContext(ConversationContext);
}
