"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";

import { tokens } from "@/lib/api";
import { ConversationContext } from "@/lib/conversation-context";
import { useStore } from "@/lib/store";
import { useKeyboardShortcuts } from "@/lib/shortcuts";
import { socket } from "@/lib/ws";
import { ConversationList } from "@/components/ConversationList";
import { NavRail } from "@/components/NavRail";
import { Toasts } from "@/components/Toasts";
import { InfoModal } from "@/components/modals/InfoModal";
import { NewChatModal, NewGroupModal } from "@/components/modals/NewChatModal";
import { ProfileModal } from "@/components/modals/ProfileModal";
import { SettingsModal } from "@/components/modals/SettingsModal";
import { ShortcutsModal } from "@/components/modals/ShortcutsModal";
import { SignalLogo } from "@/components/icons";

/**
 * The app shell. It stays mounted across conversation navigation, which is what
 * keeps the WebSocket, the store and the conversation list alive while the
 * chat pane swaps underneath it.
 */
export default function ChatsLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ id?: string }>();

  const booted = useStore((state) => state.booted);
  const me = useStore((state) => state.me);
  const boot = useStore((state) => state.boot);
  const conversations = useStore((state) => state.conversations);

  const [newChat, setNewChat] = useState(false);
  const [newGroup, setNewGroup] = useState(false);
  const [profile, setProfile] = useState(false);
  const [settings, setSettings] = useState(false);
  const [info, setInfo] = useState(false);
  const [shortcuts, setShortcuts] = useState(false);

  const activeId = params?.id ?? null;
  const activeConversation = conversations.find((c) => c.id === activeId) ?? null;

  useEffect(() => {
    void boot();
    return () => socket.disconnect();
  }, [boot]);

  useEffect(() => {
    if (booted && !me) router.replace("/login");
  }, [booted, me, router]);

  // Reconnect the socket when the tab comes back after being backgrounded.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && tokens.access) socket.connect();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem("signal.theme");
    if (stored === "light" || stored === "dark") {
      useStore.setState({ theme: stored });
      document.documentElement.dataset.theme = stored;
    }
  }, []);

  const closeEverything = useCallback(() => {
    setNewChat(false);
    setNewGroup(false);
    setProfile(false);
    setSettings(false);
    setInfo(false);
    setShortcuts(false);
  }, []);

  const shortcutHandlers = useMemo(
    () => ({
      onSearch: () => {
        const field = document.querySelector<HTMLInputElement>(
          "input[aria-label='Search chats']",
        );
        field?.focus();
        field?.select();
      },
      onNewChat: () => setNewChat(true),
      onNewGroup: () => setNewGroup(true),
      onSettings: () => setSettings(true),
      onInfo: () => {
        if (activeId) setInfo(true);
      },
      onToggleTheme: () => useStore.getState().toggleTheme(),
      onHelp: () => setShortcuts((open) => !open),
      onEscape: closeEverything,
      onMoveConversation: (direction: 1 | -1) => {
        const list = useStore.getState().conversations;
        if (!list.length) return;
        const index = list.findIndex((c) => c.id === activeId);
        const next = index === -1 ? 0 : (index + direction + list.length) % list.length;
        router.push(`/chats/${list[next].id}`);
      },
    }),
    [activeId, closeEverything, router],
  );

  useKeyboardShortcuts(shortcutHandlers, booted && Boolean(me));

  if (!booted || !me) {
    return (
      <main className="flex h-dvh items-center justify-center bg-sig-bg">
        <SignalLogo size={40} className="animate-pulse text-ultramarine" />
      </main>
    );
  }

  const onConversationRoute = pathname !== "/chats";

  return (
    <div className="flex h-dvh overflow-hidden bg-sig-bg">
      <NavRail
        onOpenSettings={() => setSettings(true)}
        onOpenProfile={() => setProfile(true)}
      />

      {/* On phones the list and the thread are separate screens, as in Signal. */}
      <div className={`${onConversationRoute ? "hidden md:flex" : "flex"} h-full`}>
        <ConversationList
          activeId={activeId}
          onNewChat={() => setNewChat(true)}
          onOpenProfile={() => setProfile(true)}
        />
      </div>

      <div
        className={`${onConversationRoute ? "flex" : "hidden md:flex"} h-full min-w-0 flex-1`}
      >
        <ConversationContext.Provider value={{ openInfo: () => setInfo(true) }}>
          {children}
        </ConversationContext.Provider>
      </div>

      <NewChatModal
        open={newChat}
        onClose={() => setNewChat(false)}
        onNewGroup={() => setNewGroup(true)}
      />
      <NewGroupModal open={newGroup} onClose={() => setNewGroup(false)} />
      <ProfileModal open={profile} onClose={() => setProfile(false)} />
      <SettingsModal
        open={settings}
        onClose={() => setSettings(false)}
        onOpenProfile={() => setProfile(true)}
        onOpenShortcuts={() => setShortcuts(true)}
      />
      <InfoModal
        open={info}
        onClose={() => setInfo(false)}
        conversation={activeConversation}
      />
      <ShortcutsModal open={shortcuts} onClose={() => setShortcuts(false)} />

      <Toasts />
    </div>
  );
}
